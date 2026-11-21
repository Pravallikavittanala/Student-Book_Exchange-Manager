# Student Book Exchange Manager — Authentication Edition

A beginner-friendly Flask + SQLite college mini-project featuring student registration/login, a colorful responsive dashboard, book listings, search and exchange requests.

## Setup on Windows (PowerShell)

```powershell
py -m venv venv
.\venv\Scripts\python.exe -m pip install -r requirements.txt
$env:DISABLE_SQLALCHEMY_CEXT = "1"
.\venv\Scripts\python.exe run.py
```

Visit http://127.0.0.1:5000 . On first use, choose **Create account**.

## Existing users from the previous ZIP

If you replace the code in your **existing project folder**, keep `instance/book_exchange.db` to preserve your existing records. The application adds a `password_hash` column automatically. Old profiles without passwords **cannot log in**; register a new account with a new email address. Existing books remain in the database under their original owners. If you extract to a new folder, a new database is created and old data is not copied automatically.

## How it works

- `run.py`: launches the Flask app.
- `app.py`: models, database setup, registration, login, session management, book CRUD, search and exchange requests.
- `templates/`: HTML/Jinja pages.
- `static/style.css`: responsive backgrounds, cards, navigation and forms.
- `tests/test_app.py`: automated checks for login, ownership and requests.
- `instance/book_exchange.db`: automatically generated SQLite database (not in the ZIP).

## Test

```powershell
$env:DISABLE_SQLALCHEMY_CEXT = "1"
.\venv\Scripts\python.exe -m pytest -q
```

## Security and scope

Passwords are hashed with Werkzeug; logged-in users have server-signed sessions. Book editing/deletion and request decisions are restricted to owners. POST forms include a CSRF token. This is a **local educational prototype**; before public deployment, configure a strong secret key, HTTPS, secure cookies, account recovery and deployment protections. Do not use real passwords for a demo.
