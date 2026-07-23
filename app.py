from flask import Flask, jsonify, render_template, request, redirect, url_for, session
from flask_sqlalchemy import SQLAlchemy
from flask_mail import Mail, Message
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv
from ariadne import graphql_sync
from ariadne.explorer import ExplorerGraphiQL
import secrets
import os

import services
import graphql_schema

load_dotenv()

app = Flask(__name__)
app.secret_key = 'dev-secret-key'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///bookclub.db'

ADMIN_EMAIL = 'admin@bookclub.test'
ADMIN_PASSWORD = 'admin123'

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


@app.context_processor
def inject_admin_context():
    if session.get('is_admin'):
        return {'is_admin': True, 'all_users': User.query.order_by(User.name).all()}
    return {'is_admin': False, 'all_users': []}


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    preferences = db.Column(db.String(500))

    def set_password(self, password):
        self.password_hash = generate_password_hash(password, method='pbkdf2:sha256')

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
    if not app.config.get('MAIL_USERNAME'):
        print(f"\n[EMAIL] To: {to}\nSubject: {subject}\n{body}\n")
        return
    try:
        msg = Message(subject=subject, recipients=[to], body=body)
        mail.send(msg)
    except Exception as e:
        print(f"[EMAIL ERROR] {e}")


_graphql_explorer_html = ExplorerGraphiQL().html(None)


@app.route('/graphql', methods=['GET'])
def graphql_explorer():
    return _graphql_explorer_html, 200


@app.route('/graphql', methods=['POST'])
def graphql_server():
    data = request.get_json()
    success, result = graphql_sync(
        graphql_schema.schema,
        data,
        context_value=graphql_schema.get_context_value(request),
        debug=app.debug,
    )
    return jsonify(result), 200 if success else 400


@app.route('/admin')
def admin_panel():
    if not session.get('is_admin'):
        return redirect(url_for('login'))
    return render_template('admin.html', users=User.query.order_by(User.name).all())


@app.route('/admin/switch/<int:user_id>')
def admin_switch(user_id):
    if not session.get('is_admin'):
        return redirect(url_for('login'))
    user = User.query.get(user_id)
    if user:
        session['user_id'] = user.id
        session['user_name'] = user.name
    next_page = request.args.get('next', '')
    return redirect(next_page or url_for('dashboard'))


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/dashboard')
def dashboard():
    if not session.get('user_id'):
        return redirect(url_for('login'))
    user = User.query.get(session['user_id'])

    memberships = GroupMembership.query.filter_by(user_id=session['user_id'], status='approved').all()
    groups = [Group.query.get(m.group_id) for m in memberships]

    upcoming_meetings = []
    for group in groups:
        for schedule in services.get_schedules(group.id, timeout=2):
            if schedule['confirmed_slot'] is not None:
                slot = schedule['slots'][schedule['confirmed_slot']]
                upcoming_meetings.append({
                    'group': group,
                    'slot_text': slot['text'],
                    'book': schedule.get('book', ''),
                })

    return render_template('dashboard.html', user=user, upcoming_meetings=upcoming_meetings)


@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    next_page = request.args.get('next', '')
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        next_page = request.form.get('next', '')
        if email == ADMIN_EMAIL and password == ADMIN_PASSWORD:
            session['is_admin'] = True
            session['user_id'] = None
            session['user_name'] = 'Admin'
            return redirect(url_for('admin_panel'))
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
            services.invite_late_joiner_to_meetings(group.id, requester)
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
            services.invite_late_joiner_to_meetings(group.id, User.query.get(session['user_id']))
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

    polls = services.get_polls(group_id)
    schedules = services.get_schedules(group_id)
    meetings = services.get_meetings(group_id)

    return render_template('club_detail.html', group=group, members=members,
                           is_member=is_member, is_creator=is_creator, creator=creator,
                           polls=polls, schedules=schedules, meetings=meetings,
                           user_id=str(session['user_id']))


@app.route('/profile')
def profile():
    if not session.get('user_id'):
        return redirect(url_for('login'))
    user = User.query.get(session['user_id'])
    if not user:
        return redirect(url_for('login'))
    return render_template('profile.html', user=user)


@app.route('/generate-personality', methods=['POST'])
def generate_personality():
    if not session.get('user_id'):
        return {'error': 'Not logged in'}, 401
    user = User.query.get(session['user_id'])
    if not user:
        return {'error': 'User not found'}, 404
    # Generate on-the-fly, don't save
    personality, image = services.generate_personality(user.preferences or 'mystery, fiction')
    return {'personality': personality, 'image': image}, 200


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

    docs = services.search_open_library(search_term)
    if docs is None:
        error = 'Could not reach the book database. Please try again.'
    else:
        books = docs

    return render_template('search_books.html', books=books, query=query, error=error, auto=auto, preferences=preferences)


@app.route('/club/<int:group_id>/poll', methods=['POST'])
def create_poll(group_id):
    if not session.get('user_id'):
        return redirect(url_for('login'))
    group = Group.query.get(group_id)
    if not group or group.creator_id != session['user_id']:
        return redirect(url_for('club_detail', group_id=group_id))

    question = "What should we read next?"
    options = [o.strip() for o in request.form['options'].splitlines() if o.strip()]
    if len(options) >= 2:
        services.create_poll(group_id, question, options, session['user_id'])

    return redirect(url_for('club_detail', group_id=group_id))


def _set_up_next(group_id, winner):
    group = Group.query.get(group_id)
    if group and winner:
        group.up_next = winner
        db.session.commit()


@app.route('/club/<int:group_id>/poll/<int:poll_id>/vote', methods=['POST'])
def cast_vote(group_id, poll_id):
    if not session.get('user_id'):
        return redirect(url_for('login'))

    option_index = request.form.get('option_index')
    if option_index is not None:
        services.cast_poll_vote(poll_id, session['user_id'], int(option_index))

        member_ids = {
            str(m.user_id)
            for m in GroupMembership.query.filter_by(group_id=group_id, status='approved').all()
        }
        polls = services.get_polls(group_id)
        for poll in polls:
            if poll['poll_id'] == poll_id and not poll['closed']:
                if member_ids == set(poll['voters'].keys()):
                    services.close_poll(poll_id)
                    _set_up_next(group_id, services.winning_option(polls, poll_id))

    return redirect(url_for('club_detail', group_id=group_id))


@app.route('/club/<int:group_id>/poll/<int:poll_id>/close', methods=['POST'])
def close_poll(group_id, poll_id):
    if not session.get('user_id'):
        return redirect(url_for('login'))
    group = Group.query.get(group_id)
    if group and group.creator_id == session['user_id']:
        polls = services.get_polls(group_id)
        services.close_poll(poll_id)
        _set_up_next(group_id, services.winning_option(polls, poll_id))
    return redirect(url_for('club_detail', group_id=group_id))


@app.route('/club/<int:group_id>/schedule', methods=['POST'])
def create_schedule(group_id):
    if not session.get('user_id'):
        return redirect(url_for('login'))
    group = Group.query.get(group_id)
    if not group or group.creator_id != session['user_id']:
        return redirect(url_for('club_detail', group_id=group_id))

    slots = [s.strip() for s in request.form['slots'].splitlines() if s.strip()]
    if slots:
        services.create_schedule(group_id, slots, session['user_id'], group.current_book)

    return redirect(url_for('club_detail', group_id=group_id))


@app.route('/club/<int:group_id>/schedule/<int:schedule_id>/availability', methods=['POST'])
def submit_availability(group_id, schedule_id):
    if not session.get('user_id'):
        return redirect(url_for('login'))

    available_slots = [int(i) for i in request.form.getlist('available_slots')]
    services.submit_availability(schedule_id, session['user_id'], available_slots)

    return redirect(url_for('club_detail', group_id=group_id))


def _notify_meeting_members(group_id, meeting_id):
    members = (
        User.query
        .join(GroupMembership, GroupMembership.user_id == User.id)
        .filter(GroupMembership.group_id == group_id, GroupMembership.status == 'approved')
        .all()
    )
    services.notify_meeting_members(
        meeting_id,
        [{'user_id': str(m.id), 'email': m.email, 'name': m.name} for m in members],
    )


@app.route('/club/<int:group_id>/schedule/<int:schedule_id>/confirm', methods=['POST'])
def confirm_slot(group_id, schedule_id):
    if not session.get('user_id'):
        return redirect(url_for('login'))
    group = Group.query.get(group_id)
    if not group or group.creator_id != session['user_id']:
        return redirect(url_for('club_detail', group_id=group_id))

    slot_index = request.form.get('slot_index')
    slot_text = request.form.get('slot_text', '')
    if slot_index is not None:
        services.confirm_schedule_slot(schedule_id, int(slot_index))

        meeting_id = services.create_meeting(group_id, slot_text, session['user_id'], group.name, group.current_book)
        if meeting_id:
            _notify_meeting_members(group_id, meeting_id)

    return redirect(url_for('club_detail', group_id=group_id))


@app.route('/club/<int:group_id>/schedule/<int:schedule_id>/cancel', methods=['POST'])
def cancel_meeting(group_id, schedule_id):
    if not session.get('user_id'):
        return redirect(url_for('login'))
    group = Group.query.get(group_id)
    if not group or group.creator_id != session['user_id']:
        return redirect(url_for('club_detail', group_id=group_id))

    services.cancel_schedule(schedule_id)

    meeting_id = request.form.get('meeting_id')
    if meeting_id:
        services.cancel_meeting(meeting_id)

    return redirect(url_for('club_detail', group_id=group_id))


@app.route('/club/<int:group_id>/complete-book', methods=['POST'])
def complete_book(group_id):
    if not session.get('user_id'):
        return redirect(url_for('login'))
    group = Group.query.get(group_id)
    if not group or group.creator_id != session['user_id'] or not group.current_book:
        return redirect(url_for('club_detail', group_id=group_id))

    existing = [l.strip() for l in (group.completed_books or '').splitlines() if l.strip()]
    if group.current_book.strip() not in existing:
        existing.append(group.current_book.strip())
    group.completed_books = '\n'.join(existing)
    group.current_book = group.up_next or ''
    group.up_next = ''
    db.session.commit()

    return redirect(url_for('club_detail', group_id=group_id))


@app.route('/my-books')
def my_books():
    if not session.get('user_id'):
        return redirect(url_for('login'))

    memberships = GroupMembership.query.filter_by(user_id=session['user_id'], status='approved').all()
    groups = [Group.query.get(m.group_id) for m in memberships]

    seen = {}
    for group in groups:
        if group.completed_books:
            for line in group.completed_books.splitlines():
                title = line.strip()
                if title:
                    seen[title.lower()] = title

    books = []
    user_id_str = str(session['user_id'])
    for normalized, title in seen.items():
        user_rating = None
        user_comment = None
        for entry in services.get_ratings(normalized):
            if entry[0] == user_id_str:
                user_rating = entry[1]
                user_comment = entry[2]
                break
        books.append({'title': title, 'normalized': normalized, 'rating': user_rating, 'comment': user_comment})

    books.sort(key=lambda b: b['title'].lower())
    return render_template('my_books.html', books=books)


@app.route('/rate-book', methods=['POST'])
def rate_book():
    if not session.get('user_id'):
        return redirect(url_for('login'))

    normalized = request.form['normalized']
    rating = int(request.form['rating'])
    comment = request.form.get('comment', '').strip() or None

    services.submit_rating(normalized, session['user_id'], rating, comment)

    return redirect(url_for('my_books'))


if __name__ == '__main__':
    app.run(debug=True, host='127.0.0.1', port=5000)
