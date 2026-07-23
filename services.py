import requests

RATING_SERVICE = 'http://localhost:8000'
POLLING_SERVICE = 'http://localhost:8001'
SCHEDULING_SERVICE = 'http://localhost:8002'
INVITE_SERVICE = 'http://localhost:8003'
AI_PROMPT_SERVICE = 'http://localhost:3000'

DEFAULT_TIMEOUT = 3


class ServiceUnavailableError(Exception):
    pass


def get_schedules(group_id, timeout=DEFAULT_TIMEOUT):
    try:
        resp = requests.get(
            f'{SCHEDULING_SERVICE}/schedules',
            params={'app_id': 'book_club', 'entity_id': str(group_id)},
            timeout=timeout,
        )
        if resp.status_code == 200:
            return resp.json()
    except Exception:
        pass
    return []


def create_schedule(group_id, slots, created_by, book, required=False):
    try:
        requests.post(
            f'{SCHEDULING_SERVICE}/schedules',
            json={
                'app_id': 'book_club',
                'entity_id': str(group_id),
                'slots': slots,
                'created_by': str(created_by),
                'book': book or '',
            },
            timeout=DEFAULT_TIMEOUT,
        )
    except Exception:
        if required:
            raise ServiceUnavailableError('scheduling service unavailable')


def submit_availability(schedule_id, user_id, available_slots, required=False):
    try:
        requests.post(
            f'{SCHEDULING_SERVICE}/schedules/{schedule_id}/availability',
            json={'user_id': str(user_id), 'available_slots': available_slots},
            timeout=DEFAULT_TIMEOUT,
        )
    except Exception:
        if required:
            raise ServiceUnavailableError('scheduling service unavailable')


def confirm_schedule_slot(schedule_id, slot_index, required=False):
    try:
        requests.post(
            f'{SCHEDULING_SERVICE}/schedules/{schedule_id}/confirm',
            json={'slot_index': slot_index},
            timeout=DEFAULT_TIMEOUT,
        )
    except Exception:
        if required:
            raise ServiceUnavailableError('scheduling service unavailable')


def cancel_schedule(schedule_id, required=False):
    try:
        requests.delete(f'{SCHEDULING_SERVICE}/schedules/{schedule_id}', timeout=DEFAULT_TIMEOUT)
    except Exception:
        if required:
            raise ServiceUnavailableError('scheduling service unavailable')


def get_polls(group_id, timeout=DEFAULT_TIMEOUT):
    try:
        resp = requests.get(
            f'{POLLING_SERVICE}/polls',
            params={'app_id': 'book_club', 'entity_id': str(group_id)},
            timeout=timeout,
        )
        if resp.status_code == 200:
            return resp.json()
    except Exception:
        pass
    return []


def create_poll(group_id, question, options, created_by, required=False):
    try:
        requests.post(
            f'{POLLING_SERVICE}/polls',
            json={
                'app_id': 'book_club',
                'entity_id': str(group_id),
                'question': question,
                'options': options,
                'created_by': str(created_by),
            },
            timeout=DEFAULT_TIMEOUT,
        )
    except Exception:
        if required:
            raise ServiceUnavailableError('polling service unavailable')


def cast_poll_vote(poll_id, user_id, option_index, required=False):
    try:
        requests.post(
            f'{POLLING_SERVICE}/polls/{poll_id}/vote',
            json={'user_id': str(user_id), 'option_index': option_index},
            timeout=DEFAULT_TIMEOUT,
        )
    except Exception:
        if required:
            raise ServiceUnavailableError('polling service unavailable')


def close_poll(poll_id, required=False):
    try:
        requests.post(f'{POLLING_SERVICE}/polls/{poll_id}/close', timeout=DEFAULT_TIMEOUT)
    except Exception:
        if required:
            raise ServiceUnavailableError('polling service unavailable')


def winning_option(polls, poll_id):
    for poll in polls:
        if poll['poll_id'] == poll_id:
            options = poll['options']
            if options:
                return max(options, key=lambda o: o['votes'])['text']
    return None


def get_meetings(group_id, timeout=DEFAULT_TIMEOUT):
    try:
        resp = requests.get(
            f'{INVITE_SERVICE}/meetings',
            params={'app_id': 'book_club', 'entity_id': str(group_id)},
            timeout=timeout,
        )
        if resp.status_code == 200:
            return resp.json()
    except Exception:
        pass
    return []


def create_meeting(group_id, slot_text, created_by, group_name, book):
    try:
        resp = requests.post(
            f'{INVITE_SERVICE}/meetings',
            json={
                'app_id': 'book_club',
                'entity_id': str(group_id),
                'slot_text': slot_text,
                'created_by': str(created_by),
                'group_name': group_name,
                'book': book or '',
            },
            timeout=DEFAULT_TIMEOUT,
        )
        return resp.json().get('meeting_id')
    except Exception:
        return None


def notify_meeting_members(meeting_id, members):
    try:
        requests.post(
            f'{INVITE_SERVICE}/meetings/{meeting_id}/members',
            json={'members': members},
            timeout=5,
        )
    except Exception:
        pass


def cancel_meeting(meeting_id):
    if not meeting_id:
        return
    try:
        requests.post(f'{INVITE_SERVICE}/meetings/{meeting_id}/cancel', timeout=5)
    except Exception:
        pass


def invite_late_joiner_to_meetings(group_id, user):
    try:
        resp = requests.get(
            f'{INVITE_SERVICE}/meetings',
            params={'app_id': 'book_club', 'entity_id': str(group_id)},
            timeout=DEFAULT_TIMEOUT,
        )
        for meeting in resp.json():
            requests.post(
                f'{INVITE_SERVICE}/meetings/{meeting["meeting_id"]}/members',
                json={'members': [{'user_id': str(user.id), 'email': user.email, 'name': user.name}]},
                timeout=5,
            )
    except Exception:
        pass


def get_ratings(normalized_title, timeout=DEFAULT_TIMEOUT):
    try:
        resp = requests.get(
            f'{RATING_SERVICE}/ratings',
            params={'app_id': 'book_club', 'entity_id': normalized_title},
            timeout=timeout,
        )
        if resp.status_code == 200:
            return resp.json().get('ratings', [])
    except Exception:
        pass
    return []


def submit_rating(normalized_title, user_id, rating, comment, required=False):
    try:
        requests.post(
            f'{RATING_SERVICE}/ratings',
            json={
                'app_id': 'book_club',
                'entity_id': normalized_title,
                'user_id': str(user_id),
                'rating': rating,
                'comment': comment,
            },
            timeout=DEFAULT_TIMEOUT,
        )
    except Exception:
        if required:
            raise ServiceUnavailableError('rating service unavailable')


def generate_personality(preferences):
    """Call AI service for a text personality + base64 image. Never raises."""
    try:
        text_response = requests.post(
            f'{AI_PROMPT_SERVICE}/generate',
            json={
                'prompt': f"Give me a one or two word book personality for someone who likes: "
                          f"{preferences}. Just the personality phrase, nothing else."
            },
            timeout=10,
        )
        if text_response.status_code != 200:
            return "I'm stumped", None

        text_data = text_response.json()
        personality = text_data.get('response') or text_data.get('personality') or 'Curious Reader'

        image_response = requests.post(
            f'{AI_PROMPT_SERVICE}/generate',
            json={
                'prompt': f"Create an simple picture representing this book personality: "
                          f"'{personality}'. Style: watercolor, literary art, elegant."
            },
            timeout=60,
        )
        image_src = None
        if image_response.status_code == 200:
            image_data = image_response.json()
            b64 = image_data.get('response') or image_data.get('image')
            if b64:
                image_src = f"data:image/png;base64,{b64}"

        return personality.strip(), image_src
    except Exception:
        return "I'm stumped", None


def search_open_library(query, limit=18):
    """Returns a list of docs on success, or None on failure (caller distinguishes 'no results' from 'error')."""
    try:
        response = requests.get(
            'https://openlibrary.org/search.json',
            params={'q': query, 'limit': limit},
            timeout=5,
        )
        return response.json().get('docs', [])
    except Exception:
        return None
