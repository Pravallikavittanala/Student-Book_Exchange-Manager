import os
import secrets
from datetime import datetime, timezone
from functools import wraps
from flask import Flask, abort, flash, g, redirect, render_template, request, session, url_for
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import or_, text
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()

class Student(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    phone = db.Column(db.String(20))
    password_hash = db.Column(db.String(255), nullable=True)
    books = db.relationship('Book', backref='owner', lazy=True)

class Book(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(150), nullable=False)
    author = db.Column(db.String(100), nullable=False)
    category = db.Column(db.String(80), nullable=False)
    condition = db.Column(db.String(30), nullable=False)
    available = db.Column(db.Boolean, nullable=False, default=True)
    owner_id = db.Column(db.Integer, db.ForeignKey('student.id'), nullable=False)
    requests = db.relationship('ExchangeRequest', backref='book', lazy=True)

class ExchangeRequest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    book_id = db.Column(db.Integer, db.ForeignKey('book.id'), nullable=False)
    requester_id = db.Column(db.Integer, db.ForeignKey('student.id'), nullable=False)
    status = db.Column(db.String(20), nullable=False, default='Pending')
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    requester = db.relationship('Student', foreign_keys=[requester_id])

def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if g.user is None:
            return redirect(url_for('login'))
        return view(*args, **kwargs)
    return wrapped

def create_app(test_config=None):
    app = Flask(__name__)
    app.config.update(SECRET_KEY=os.environ.get('SECRET_KEY', 'local-development-only-change-me'),
                      SQLALCHEMY_DATABASE_URI='sqlite:///book_exchange.db',
                      SQLALCHEMY_TRACK_MODIFICATIONS=False,
                      SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Lax')
    if test_config:
        app.config.update(test_config)
    db.init_app(app)
    with app.app_context():
        # Compatible with the previous ZIP's existing SQLite database.
        db.create_all()
        columns = [row[1] for row in db.session.execute(text('PRAGMA table_info(student)'))]
        if 'password_hash' not in columns:
            db.session.execute(text('ALTER TABLE student ADD COLUMN password_hash VARCHAR(255)'))
            db.session.commit()

    @app.before_request
    def load_user_and_check_csrf():
        g.user = db.session.get(Student, session['user_id']) if 'user_id' in session else None
        if g.user is None:
            session.pop('user_id', None)
        if '_csrf_token' not in session:
            session['_csrf_token'] = secrets.token_hex(24)
        if request.method == 'POST' and request.form.get('_csrf_token') != session['_csrf_token']:
            abort(400, 'Invalid form token. Refresh the page and try again.')

    @app.context_processor
    def globals_for_templates():
        return {'current_user': g.get('user'), 'csrf_token': session.get('_csrf_token', '')}

    @app.route('/register', methods=['GET', 'POST'])
    def register():
        if g.user:
            return redirect(url_for('home'))
        if request.method == 'POST':
            name = request.form.get('name', '').strip()
            email = request.form.get('email', '').strip().lower()
            phone = request.form.get('phone', '').strip()
            password = request.form.get('password', '')
            confirm = request.form.get('confirm', '')
            existing = Student.query.filter_by(email=email).first()
            if not name or len(name) > 100 or not email or '@' not in email or email.startswith('@') or email.endswith('@') or len(email) > 120:
                flash('Enter a valid name and email.', 'error')
            elif len(password) < 8:
                flash('Password must have at least 8 characters.', 'error')
            elif password != confirm:
                flash('Passwords do not match.', 'error')
            elif existing:
                flash('This email already exists. If it was in the older version, use a different email; old profiles have no login password.', 'error')
            else:
                student = Student(name=name, email=email, phone=phone, password_hash=generate_password_hash(password))
                db.session.add(student)
                db.session.commit()
                session.clear()
                session['user_id'] = student.id
                flash('Account created successfully. Welcome!', 'success')
                return redirect(url_for('home'))
        return render_template('register.html')

    @app.route('/login', methods=['GET', 'POST'])
    def login():
        if g.user:
            return redirect(url_for('home'))
        if request.method == 'POST':
            email = request.form.get('email', '').strip().lower()
            password = request.form.get('password', '')
            student = Student.query.filter_by(email=email).first()
            if not student or not student.password_hash or not check_password_hash(student.password_hash, password):
                flash('Invalid email or password.', 'error')
            else:
                session.clear()
                session['user_id'] = student.id
                flash('Welcome back!', 'success')
                return redirect(url_for('home'))
        return render_template('login.html')

    @app.post('/logout')
    @login_required
    def logout():
        session.clear()
        flash('You have logged out.', 'success')
        return redirect(url_for('login'))

    @app.get('/')
    @login_required
    def home():
        return render_template('index.html', student_count=Student.query.filter(Student.password_hash.isnot(None)).count(),
            book_count=Book.query.count(), available_count=Book.query.filter_by(available=True).count(),
            request_count=ExchangeRequest.query.filter(or_(ExchangeRequest.requester_id == g.user.id,
            ExchangeRequest.book_id.in_(db.session.query(Book.id).filter_by(owner_id=g.user.id)))).count(),
            my_books=Book.query.filter_by(owner_id=g.user.id).count())

    @app.get('/students')
    @login_required
    def students():
        return render_template('students.html', students=Student.query.filter(Student.password_hash.isnot(None)).order_by(Student.name).all())

    @app.route('/students/<int:student_id>/edit', methods=['GET', 'POST'])
    @login_required
    def edit_student(student_id):
        if student_id != g.user.id:
            abort(403)
        student = g.user
        if request.method == 'POST':
            name = request.form.get('name', '').strip()
            email = request.form.get('email', '').strip().lower()
            phone = request.form.get('phone', '').strip()
            duplicate = Student.query.filter(Student.email == email, Student.id != student.id).first()
            if not name or len(name) > 100 or not email or '@' not in email or len(email) > 120 or duplicate:
                flash('Provide a name and a unique valid email.', 'error')
            else:
                student.name, student.email, student.phone = name, email, phone
                db.session.commit()
                flash('Profile updated.', 'success')
                return redirect(url_for('students'))
        return render_template('student_form.html', student=student)

    @app.get('/books')
    @login_required
    def books():
        q = request.args.get('q', '').strip()
        category = request.args.get('category', '').strip()
        availability = request.args.get('availability', 'all')
        query = Book.query
        if q:
            query = query.filter(or_(Book.title.ilike(f'%{q}%'), Book.author.ilike(f'%{q}%')))
        if category:
            query = query.filter(Book.category.ilike(f'%{category}%'))
        if availability == 'available':
            query = query.filter_by(available=True)
        elif availability == 'unavailable':
            query = query.filter_by(available=False)
        return render_template('books.html', books=query.order_by(Book.id.desc()).all(), q=q, category=category, availability=availability)

    @app.route('/books/add', methods=['GET', 'POST'])
    @login_required
    def add_book():
        if request.method == 'POST':
            title, author, category, condition = [request.form.get(k, '').strip() for k in ('title','author','category','condition')]
            if not title or not author or not category or len(title)>150 or len(author)>100 or len(category)>80 or condition not in ('New','Good','Fair'):
                flash('Enter valid book details.', 'error')
            else:
                db.session.add(Book(title=title, author=author, category=category, condition=condition, owner_id=g.user.id))
                db.session.commit()
                flash('Your book was added!', 'success')
                return redirect(url_for('books'))
        return render_template('book_form.html', book=None)

    @app.route('/books/<int:book_id>/edit', methods=['GET', 'POST'])
    @login_required
    def edit_book(book_id):
        book = db.get_or_404(Book, book_id)
        if book.owner_id != g.user.id:
            abort(403)
        if request.method == 'POST':
            title, author, category, condition = [request.form.get(k, '').strip() for k in ('title','author','category','condition')]
            if not title or not author or not category or len(title)>150 or len(author)>100 or len(category)>80 or condition not in ('New','Good','Fair'):
                flash('Enter valid book details.', 'error')
            else:
                book.title, book.author, book.category, book.condition = title, author, category, condition
                db.session.commit()
                flash('Book updated.', 'success')
                return redirect(url_for('books'))
        return render_template('book_form.html', book=book)

    @app.post('/books/<int:book_id>/delete')
    @login_required
    def delete_book(book_id):
        book = db.get_or_404(Book, book_id)
        if book.owner_id != g.user.id:
            abort(403)
        if ExchangeRequest.query.filter_by(book_id=book.id).first():
            flash('Cannot delete a book with exchange requests.', 'error')
        else:
            db.session.delete(book)
            db.session.commit()
            flash('Book deleted.', 'success')
        return redirect(url_for('books'))

    @app.route('/requests', methods=['GET', 'POST'])
    @login_required
    def exchange_requests():
        if request.method == 'POST':
            book_id = request.form.get('book_id', type=int)
            book = db.session.get(Book, book_id) if book_id is not None else None
            if not book or not book.available:
                flash('Select an available book.', 'error')
            elif book.owner_id == g.user.id:
                flash('You cannot request your own book.', 'error')
            elif ExchangeRequest.query.filter_by(book_id=book.id, requester_id=g.user.id, status='Pending').first():
                flash('You already have a pending request for this book.', 'error')
            else:
                db.session.add(ExchangeRequest(book_id=book.id, requester_id=g.user.id))
                db.session.commit()
                flash('Request sent to the owner!', 'success')
                return redirect(url_for('exchange_requests'))
        relevant = ExchangeRequest.query.join(Book).filter(or_(ExchangeRequest.requester_id == g.user.id, Book.owner_id == g.user.id)).order_by(ExchangeRequest.id.desc()).all()
        available = Book.query.filter(Book.available.is_(True), Book.owner_id != g.user.id).order_by(Book.title).all()
        return render_template('requests.html', requests=relevant, books=available)

    @app.post('/requests/<int:request_id>/<action>')
    @login_required
    def update_request(request_id, action):
        exchange = db.get_or_404(ExchangeRequest, request_id)
        if exchange.book.owner_id != g.user.id:
            abort(403)
        if action in ('accept', 'reject') and exchange.status == 'Pending':
            if action == 'accept':
                if not exchange.book.available:
                    flash('Book is no longer available.', 'error')
                    return redirect(url_for('exchange_requests'))
                exchange.status = 'Accepted'
                exchange.book.available = False
                for other in ExchangeRequest.query.filter_by(book_id=exchange.book_id, status='Pending').all():
                    if other.id != exchange.id:
                        other.status = 'Rejected'
            else:
                exchange.status = 'Rejected'
        elif action == 'complete' and exchange.status == 'Accepted':
            exchange.status = 'Completed'
        else:
            flash('This status change is not allowed.', 'error')
            return redirect(url_for('exchange_requests'))
        db.session.commit()
        flash('Request updated.', 'success')
        return redirect(url_for('exchange_requests'))

    return app
