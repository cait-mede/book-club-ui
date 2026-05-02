from flask import Flask, render_template, request, redirect, url_for, session
from flask_sqlalchemy import SQLAlchemy
from flask_mail import Mail, Message
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv
import requests
import secrets
import os

load_dotenv()

app = Flask(__name__)
app.secret_key = 'dev-secret-key'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///bookclub.db'

# ----- EMAIL CONFIG -----
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD')
app.config['MAIL_DEFAULT_SENDER'] = os.environ.get('MAIL_USERNAME')
# ------------------------

db = SQLAlchemy(app)
mail = Mail(app)


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    preferences = db.Column(db.String(500))

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Group(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.String(500))
    genre = db.Column(db.String(50))
    reading_pace = db.Column(db.String(50))
    current_book = db.Column(db.String(200))
    up_next = db.Column(db.String(200))
    completed_books = db.Column(db.Text)
    creator_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    memberships = db.relationship('GroupMembership', backref='group', lazy=True)

    def member_count(self):
        return GroupMembership.query.filter_by(group_id=self.id, status='approved').count()


class GroupMembership(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    group_id = db.Column(db.Integer, db.ForeignKey('group.id'), nullable=False)
    status = db.Column(db.String(20), default='pending')


class GroupInvite(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    group_id = db.Column(db.Integer, db.ForeignKey('group.id'), nullable=False)
    email = db.Column(db.String(120), nullable=False)
    token = db.Column(db.String(64), unique=True, nullable=False)
    used = db.Column(db.Boolean, default=False)


with app.app_context():
    db.create_all()


def send_email(to, subject, body):
    try:
        msg = Message(subject=subject, recipients=[to], body=body)
        mail.send(msg)
    except Exception:
        pass


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/dashboard')
def dashboard():
    if not session.get('user_id'):
        return redirect(url_for('login'))
    return render_template('dashboard.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    next_page = request.args.get('next', '')
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        next_page = request.form.get('next', '')
        user = User.query.filter_by(email=email).first()
        if user and user.check_password(password):
            session['user_id'] = user.id
            session['user_name'] = user.name
            return redirect(next_page or url_for('dashboard'))
        else:
            error = 'Invalid email or password.'
    return render_template('login.html', error=error, next=next_page)


@app.route('/signup', methods=['GET', 'POST'])
def signup():
    error = None
    next_page = request.args.get('next', '')
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        password = request.form['password']
        preferences = request.form['preferences']
        next_page = request.form.get('next', '')
        if User.query.filter_by(email=email).first():
            error = 'An account with that email already exists.'
        else:
            user = User(name=name, email=email, preferences=preferences)
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
            session['user_id'] = user.id
            session['user_name'] = user.name
            return redirect(next_page or url_for('dashboard'))
    return render_template('signup.html', error=error, next=next_page)


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))


@app.route('/create-group', methods=['GET', 'POST'])
def create_group():
    if not session.get('user_id'):
        return redirect(url_for('login'))
    if request.method == 'POST':
        name = request.form['name']
        description = request.form['description']
        genre = request.form['genre']
        reading_pace = request.form['reading_pace']
        current_book = request.form.get('current_book', '')
        up_next = request.form.get('up_next', '')
        completed_books = request.form.get('completed_books', '')
        group = Group(
            name=name,
            description=description,
            genre=genre,
            reading_pace=reading_pace,
            current_book=current_book,
            up_next=up_next,
            completed_books=completed_books,
            creator_id=session['user_id']
        )
        db.session.add(group)
        db.session.flush()
        membership = GroupMembership(user_id=session['user_id'], group_id=group.id, status='approved')
        db.session.add(membership)
        db.session.commit()
        return redirect(url_for('my_groups'))
    return render_template('create_group.html')


@app.route('/join-group')
def join_group():
    if not session.get('user_id'):
        return redirect(url_for('login'))
    search = request.args.get('search', '')
    if search:
        groups = Group.query.filter(Group.name.ilike(f'%{search}%')).all()
    else:
        groups = Group.query.all()
    approved_ids = [m.group_id for m in GroupMembership.query.filter_by(user_id=session['user_id'], status='approved').all()]
    pending_ids = [m.group_id for m in GroupMembership.query.filter_by(user_id=session['user_id'], status='pending').all()]
    return render_template('join_group.html', groups=groups, search=search, approved_ids=approved_ids, pending_ids=pending_ids)


@app.route('/join-group/<int:group_id>/request', methods=['POST'])
def request_join(group_id):
    if not session.get('user_id'):
        return redirect(url_for('login'))
    existing = GroupMembership.query.filter_by(user_id=session['user_id'], group_id=group_id).first()
    if not existing:
        membership = GroupMembership(user_id=session['user_id'], group_id=group_id, status='pending')
        db.session.add(membership)
        db.session.commit()

        group = Group.query.get(group_id)
        creator = User.query.get(group.creator_id)
        requester = User.query.get(session['user_id'])
        approve_link = url_for('approve_member', membership_id=membership.id, _external=True)
        send_email(
            to=creator.email,
            subject=f'New request to join {group.name}',
            body=(
                f'Hi {creator.name},\n\n'
                f'{requester.name} ({requester.email}) has requested to join your book club "{group.name}".\n\n'
                f'Click the link below to accept or decline their request:\n{approve_link}\n\n'
                f'- Book Club App'
            )
        )
    return redirect(url_for('join_group'))


@app.route('/approve/<int:membership_id>', methods=['GET', 'POST'])
def approve_member(membership_id):
    membership = GroupMembership.query.get(membership_id)
    if not membership:
        return redirect(url_for('my_groups'))
    group = Group.query.get(membership.group_id)
    creator = User.query.get(group.creator_id)
    approve_url = url_for('approve_member', membership_id=membership_id, _external=False)
    if not session.get('user_id'):
        return redirect(url_for('login', next=approve_url))
    if session['user_id'] != group.creator_id:
        return render_template('approve.html', wrong_account=True,
                               creator_email=creator.email, approve_url=approve_url,
                               group=None, requester=None)
    requester = User.query.get(membership.user_id)
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'accept':
            membership.status = 'approved'
            db.session.commit()
            send_email(
                to=requester.email,
                subject=f'You have been approved to join {group.name}!',
                body=(
                    f'Hi {requester.name},\n\n'
                    f'Your request to join "{group.name}" has been approved!\n\n'
                    f'Log in to see your group.\n\n'
                    f'- Book Club App'
                )
            )
        elif action == 'decline':
            db.session.delete(membership)
            db.session.commit()
            send_email(
                to=requester.email,
                subject=f'Update on your request to join {group.name}',
                body=(
                    f'Hi {requester.name},\n\n'
                    f'Unfortunately your request to join "{group.name}" was not approved at this time.\n\n'
                    f'- Book Club App'
                )
            )
        return redirect(url_for('my_groups'))
    return render_template('approve.html', wrong_account=False, membership=membership, group=group, requester=requester)


@app.route('/my-groups')
def my_groups():
    if not session.get('user_id'):
        return redirect(url_for('login'))
    memberships = GroupMembership.query.filter_by(user_id=session['user_id'], status='approved').all()
    groups = [Group.query.get(m.group_id) for m in memberships]
    created_groups = Group.query.filter_by(creator_id=session['user_id']).all()
    pending_requests = []
    for group in created_groups:
        pending = GroupMembership.query.filter_by(group_id=group.id, status='pending').all()
        for p in pending:
            requester = User.query.get(p.user_id)
            pending_requests.append({'membership': p, 'group': group, 'requester': requester})
    return render_template('my_groups.html', groups=groups, pending_requests=pending_requests)


@app.route('/invite/<int:group_id>', methods=['GET', 'POST'])
def invite(group_id):
    if not session.get('user_id'):
        return redirect(url_for('login'))
    group = Group.query.get(group_id)
    sent = False
    if request.method == 'POST':
        invite_email = request.form['invite_email']
        token = secrets.token_urlsafe(32)
        group_invite = GroupInvite(group_id=group_id, email=invite_email, token=token)
        db.session.add(group_invite)
        db.session.commit()
        accept_link = url_for('accept_invite', token=token, _external=True)
        send_email(
            to=invite_email,
            subject=f"You've been invited to join {group.name} on Book Club!",
            body=(
                f'Hi there!\n\n'
                f'{session["user_name"]} has invited you to join their book club "{group.name}".\n\n'
                f'Click the link below to accept the invite. You will be asked to log in or create an account first.\n\n'
                f'{accept_link}\n\n'
                f'- Book Club App'
            )
        )
        sent = True
    return render_template('invite.html', group=group, sent=sent)


@app.route('/accept-invite/<token>', methods=['GET', 'POST'])
def accept_invite(token):
    group_invite = GroupInvite.query.filter_by(token=token, used=False).first()
    if not group_invite:
        return render_template('accept_invite.html', invalid=True)
    group = Group.query.get(group_invite.group_id)
    accept_url = url_for('accept_invite', token=token, _external=False)
    if not session.get('user_id'):
        return redirect(url_for('login', next=accept_url))
    current_user = User.query.get(session['user_id'])
    if current_user.email != group_invite.email:
        return render_template('accept_invite.html', group=group, invalid=False, wrong_account=True,
                               invite_email=group_invite.email, accept_url=accept_url)
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'accept':
            existing = GroupMembership.query.filter_by(user_id=session['user_id'], group_id=group.id).first()
            if not existing:
                membership = GroupMembership(user_id=session['user_id'], group_id=group.id, status='approved')
                db.session.add(membership)
            group_invite.used = True
            db.session.commit()
        return redirect(url_for('my_groups'))
    return render_template('accept_invite.html', group=group, invalid=False, wrong_account=False)


@app.route('/club/<int:group_id>')
def club_detail(group_id):
    if not session.get('user_id'):
        return redirect(url_for('login'))
    group = Group.query.get(group_id)
    if not group:
        return redirect(url_for('my_groups'))
    members = (
        db.session.query(User)
        .join(GroupMembership, GroupMembership.user_id == User.id)
        .filter(GroupMembership.group_id == group_id, GroupMembership.status == 'approved')
        .all()
    )
    is_member = any(m.id == session['user_id'] for m in members)
    is_creator = group.creator_id == session['user_id']
    creator = User.query.get(group.creator_id)
    return render_template('club_detail.html', group=group, members=members,
                           is_member=is_member, is_creator=is_creator, creator=creator)


@app.route('/search-books')
def search_books():
    if not session.get('user_id'):
        return redirect(url_for('login'))
    query = request.args.get('q', '')
    books = []
    error = None
    auto = False

    user = User.query.get(session['user_id'])
    preferences = user.preferences if user.preferences else ''

    search_term = query if query else preferences if preferences else 'popular fiction'
    if not query:
        auto = True

    try:
        response = requests.get(
            'https://openlibrary.org/search.json',
            params={'q': search_term, 'limit': 18},
            timeout=5
        )
        books = response.json().get('docs', [])
    except Exception:
        error = 'Could not reach the book database. Please try again.'

    return render_template('search_books.html', books=books, query=query, error=error, auto=auto, preferences=preferences)


if __name__ == '__main__':
    app.run(debug=True)
