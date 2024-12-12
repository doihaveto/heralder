from flask import Blueprint, request, render_template, redirect, url_for, request, flash
from typing import Optional
from datetime import datetime
from database import db
from flask_login import UserMixin, login_user, logout_user, login_required, current_user
from sqlalchemy.orm import Mapped, mapped_column
from werkzeug.security import generate_password_hash, check_password_hash

class User(db.Model, UserMixin):
    __tablename__ = 'users'

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(db.String(80), unique=True)
    password_hash: Mapped[str] = mapped_column(db.String(128))
    created_date: Mapped[datetime] = mapped_column(db.DateTime, default=datetime.utcnow)
    is_superuser: Mapped[bool] = mapped_column(db.Boolean, default=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

def load_user(user_id):
    return User.query.get(int(user_id))

blueprint = Blueprint('users', __name__)

@blueprint.route('/login/', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    if not User.query.count():
        default_admin = User(username='admin', password_hash=generate_password_hash('admin'), is_superuser=True)
        db.session.add(default_admin)
        db.session.commit()
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            login_user(user)
            return redirect(url_for('index'))
        else:
            error = 'Invalid password'
        return render_template('users/login.html', error=error), 403
    return render_template('users/login.html', error=None)

@blueprint.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('users.login'))

@blueprint.route('/users/', methods=['GET', 'POST'])
@login_required
def user_management():
    if not current_user.is_superuser:
        flash('You do not have permission to access this page.', 'danger')
        return redirect(url_for('index'))  # Redirect to your app's home page
    if request.method == 'POST':
        if request.form.get('action') == 'add_user':
            username = request.form.get('username')
            password = request.form.get('password')
            superuser = 'superuser' in request.form
            existing_user = User.query.filter_by(username=username).first()
            if not existing_user:
                hashed_password = generate_password_hash(password)
                new_user = User(username=username, password_hash=hashed_password, is_superuser=superuser)
                db.session.add(new_user)
                db.session.commit()
                flash(f'User "{username}" has been added.', 'success')
            else:
                flash(f'User "{username}" already exists.', 'warning')
        elif request.form.get('action') == 'change_password':
            username = request.form.get('username')
            new_password = request.form.get('new_password')
            user = User.query.filter_by(username=username).first()
            if user:
                hashed_password = generate_password_hash(new_password)
                user.password_hash = hashed_password
                db.session.commit()
                flash(f'Password for user "{username}" has been changed.', 'success')
            else:
                flash(f'User "{username}" does not exist.', 'warning')
        elif request.form.get('action') == 'delete_user':
            username = request.form.get('username')
            user = User.query.filter_by(username=username).first()
            if user:
                db.session.delete(user)
                db.session.commit()
                flash(f'User "{username}" has been deleted.', 'success')
            else:
                flash(f'User "{username}" does not exist.', 'warning')
    users = User.query.all()
    return render_template('users/user_management.html', users=users)
