import json
import re
from collections import Counter

from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

from .models import ChatMessage, ChatbotFAQ


ROLE_ALLOWED_INTENTS = {
    'USER': {
        'greeting', 'platform_overview', 'booking_help', 'pricing_help', 'payment_help',
        'review_help', 'profile_help', 'dashboard_help', 'support', 'thanks', 'unknown'
    },
    'STUDIO': {
        'greeting', 'platform_overview', 'booking_help', 'pricing_help', 'payment_help',
        'review_help', 'profile_help', 'dashboard_help', 'studio_ops', 'support', 'thanks', 'unknown'
    },
    'ADMIN': {
        'greeting', 'platform_overview', 'booking_help', 'payment_help', 'dashboard_help',
        'admin_ops', 'support', 'thanks', 'unknown'
    },
}

INTENT_HINT = {
    'studio_ops': 'studio-owner workflows',
    'admin_ops': 'admin workflows',
    'sensitive_data': 'private or security-sensitive information',
}

ROLE_LABELS = {
    'USER': 'user',
    'STUDIO': 'studio owner',
    'ADMIN': 'admin',
}

ROLE_RESTRICTED_PATTERNS = {
    'USER': {
        'studio_ops': [
            'studio dashboard', 'studio owner', 'portfolio', 'studio profile', 'services setup',
            'booking approval', 'approve booking', 'cancel client booking', 'earnings',
            'payout', 'commission', 'studio payout', 'owner account',
        ],
        'admin_ops': [
            'admin', 'manage users', 'manage studios', 'verify studio', 'approve studio',
            'reject studio', 'delete user', 'block user', 'moderation', 'admin panel',
            'payment control', 'payout command',
        ],
    },
    'STUDIO': {
        'admin_ops': [
            'admin', 'manage users', 'manage studios', 'verify studio', 'approve studio',
            'reject studio', 'delete user', 'block user', 'moderation', 'admin panel',
            'all platform payments', 'all users', 'all studios',
        ],
    },
    'ADMIN': {},
}

SENSITIVE_PATTERNS = [
    'password', 'otp', 'secret key', 'api key', 'private key', 'razorpay key', 'database',
    'db.sqlite', 'session cookie', 'csrf token', 'auth token', 'export all emails',
    'download user data', 'bank account number', 'upi id of user', 'license document',
    'bypass', 'hack', 'impersonate', 'login as', 'credentials',
]

ROLE_KNOWLEDGE_BASE = {
    'USER': [
        {
            'title': 'Explore and book studios',
            'keywords': ['explore', 'find', 'search', 'book', 'booking', 'studio', 'recommendation'],
            'answer': (
                "Use Explore Studios or AI Recommendations to compare verified studios. Open a studio, review "
                "portfolio, pricing, rating, and services, then choose Book Studio to submit a booking request."
            ),
        },
        {
            'title': 'Payments and refunds',
            'keywords': ['payment', 'pay', 'refund', 'transaction', 'upi', 'receipt'],
            'answer': (
                "User payments go to the StudioSync admin account first. After payment, StudioSync records the "
                "platform split and the studio payout status. You can track receipts and refund requests from Payments."
            ),
        },
        {
            'title': 'Reviews',
            'keywords': ['review', 'rating', 'feedback'],
            'answer': (
                "You can review a studio after a confirmed booking. Use Reviews to add, edit, or delete your own "
                "feedback."
            ),
        },
        {
            'title': 'Profile and notifications',
            'keywords': ['profile', 'account', 'notification', 'settings'],
            'answer': (
                "Use Profile Settings to manage your account and notification preferences. Booking and payment "
                "updates appear in Notifications."
            ),
        },
    ],
    'STUDIO': [
        {
            'title': 'Booking operations',
            'keywords': ['booking', 'approve', 'cancel', 'complete', 'schedule', 'client'],
            'answer': (
                "Use Studio Bookings to review client requests, approve valid bookings, cancel unavailable slots, "
                "send client notifications, and mark confirmed shoots completed."
            ),
        },
        {
            'title': 'Payout and earnings ledger',
            'keywords': ['earning', 'payout', 'payment', 'commission', 'transaction', 'revenue'],
            'answer': (
                "StudioSync collects client payments first. Your Earnings page shows gross paid, 10% admin "
                "commission, your 90% net payout, payout status, transfer reference, and notes."
            ),
        },
        {
            'title': 'Portfolio and profile',
            'keywords': ['portfolio', 'profile', 'service', 'price', 'cover', 'license'],
            'answer': (
                "Use Portfolio to manage work samples and Studio Profile to update studio details, services, "
                "pricing, contact information, verification items, and cover image."
            ),
        },
        {
            'title': 'Reviews and reputation',
            'keywords': ['review', 'rating', 'feedback', 'reputation'],
            'answer': (
                "Use Studio Reviews to monitor client ratings and feedback trends. Strong reviews improve trust "
                "and help users compare your studio."
            ),
        },
    ],
    'ADMIN': [
        {
            'title': 'Studio verification',
            'keywords': ['studio', 'verify', 'approve', 'reject', 'license', 'review studio'],
            'answer': (
                "Use Manage Studios to inspect license, profile, contact, location, services, portfolio, and reviews. "
                "Approve only when the verification checklist is credible."
            ),
        },
        {
            'title': 'Payment and payout command center',
            'keywords': ['payment', 'payout', 'commission', 'transaction', 'wallet', 'settlement'],
            'answer': (
                "Use Payment & Payout Command Center to audit payments collected by StudioSync, track 10% platform "
                "commission, and mark the 90% studio payout paid after recording transfer reference and notes."
            ),
        },
        {
            'title': 'User and admin management',
            'keywords': ['user', 'admin', 'manage', 'block', 'delete', 'status'],
            'answer': (
                "Use Manage Users and Manage Admins to review accounts and apply minimal necessary actions. Avoid "
                "sharing private user details outside the admin console."
            ),
        },
        {
            'title': 'Bookings oversight',
            'keywords': ['booking', 'cancel', 'monitor', 'dispute'],
            'answer': (
                "Use Bookings to monitor platform activity and intervene only when policy or support evidence requires it."
            ),
        },
    ],
}


@login_required
@require_http_methods(["GET", "POST"])
def chatbot_messages(request):
    """Backward-compatible chatbot endpoint that auto-selects the user's role."""
    return _chatbot_messages_for_role(request, expected_role=None)


@login_required
@require_http_methods(["GET", "POST"])
def chatbot_messages_user(request):
    return _chatbot_messages_for_role(request, expected_role='USER')


@login_required
@require_http_methods(["GET", "POST"])
def chatbot_messages_studio(request):
    return _chatbot_messages_for_role(request, expected_role='STUDIO')


@login_required
@require_http_methods(["GET", "POST"])
def chatbot_messages_admin(request):
    return _chatbot_messages_for_role(request, expected_role='ADMIN')


def _chatbot_messages_for_role(request, expected_role=None):
    role = get_user_role(request.user)

    if expected_role and role != expected_role:
        return JsonResponse(
            {
                'error': 'Forbidden',
                'message': f'This chatbot endpoint is restricted to {expected_role.lower()} role.',
            },
            status=403,
        )

    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            user_message = data.get('message', '').strip()

            if not user_message:
                return JsonResponse({'error': 'Message cannot be empty'}, status=400)

            ChatMessage.objects.create(
                user=request.user,
                message=user_message,
                user_message=user_message,
                is_user=True,
                role_at_message_time=role,
            )

            bot_response, blocked_reason, policy_notice, response_mode = generate_bot_response(user_message, request.user)
            was_blocked = blocked_reason is not None

            ChatMessage.objects.create(
                user=request.user,
                message=bot_response,
                response=bot_response,
                bot_response=bot_response,
                is_user=False,
                role_at_message_time=role,
                policy_blocked=was_blocked,
                blocked_reason=blocked_reason,
                response_mode=response_mode,
            )

            return JsonResponse(
                {
                    'user_message': user_message,
                    'bot_response': bot_response,
                    'success': True,
                    'role': role,
                    'policy_blocked': was_blocked,
                    'policy_notice': policy_notice,
                    'response_mode': response_mode,
                }
            )
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)
        except Exception as exc:
            return JsonResponse({'error': str(exc)}, status=500)

    messages = (
        ChatMessage.objects.filter(user=request.user)
        .filter(Q(role_at_message_time=role) | Q(role_at_message_time='UNKNOWN'))
        .order_by('timestamp')[:50]
    )
    message_list = [
        {
            'message': msg.message,
            'is_user': msg.is_user,
            'timestamp': msg.timestamp.isoformat(),
            'role': msg.role_at_message_time,
            'policy_blocked': msg.policy_blocked,
        }
        for msg in messages
    ]
    return JsonResponse({'messages': message_list, 'role': role})


def generate_bot_response(user_message, user):
    """Generate a role-safe chatbot response."""
    text = (user_message or '').strip().lower()
    role = get_user_role(user)

    if not text:
        return "Please type a question and I will help.", None, None, 'fallback'

    blocked_intent = detect_policy_violation(text, role)
    if blocked_intent:
        return build_blocked_response(role, blocked_intent)

    intent = classify_intent(text, role)
    allowed_intents = ROLE_ALLOWED_INTENTS.get(role, set())
    if intent not in allowed_intents:
        return build_blocked_response(role, intent)

    faq_answer = match_faq_answer(text, role)
    if faq_answer:
        return faq_answer, None, None, 'faq_hit'

    if intent == 'admin_ops':
        admin_response = (
            "Admin operations checklist:\n"
            "1. Confirm the target entity (user, studio, booking, or payment).\n"
            "2. Verify supporting evidence and recent activity logs.\n"
            "3. Apply the minimal action required by policy.\n"
            "4. Record reason and outcome in admin notes."
        )
        return admin_response, None, build_policy_notice(role, intent, blocked=False), 'admin_safe'

    ai_answer = generate_role_safe_ai_answer(text, role)
    if ai_answer:
        return ai_answer, None, build_policy_notice(role, intent, blocked=False), 'standard'

    if intent == 'greeting':
        return (
            "Hello! I am the StudioSync assistant. I can explain the allowed workflows for your current role."
        ), None, None, 'intent_answer'

    if intent == 'platform_overview':
        return platform_overview(user), None, None, 'intent_answer'

    if intent == 'booking_help':
        return (
            "Bookings work like this: browse studios, open a studio profile, choose a date, time slot, and any "
            "extra service, then complete payment after the booking is approved."
        ), None, None, 'intent_answer'

    if intent == 'pricing_help':
        return (
            "Pricing depends on the studio, its hourly rate, services, and any camera add-ons. You can compare "
            "studios by location, rating, and budget before booking."
        ), None, None, 'intent_answer'

    if intent == 'payment_help':
        return (
            "Payments are handled from the booking and payment pages. StudioSync collects payment first, then the "
            "platform split and studio payout status are tracked in the dashboard."
        ), None, None, 'intent_answer'

    if intent == 'review_help':
        return (
            "Reviews can be posted after a confirmed booking. Users can write, edit, or delete their own reviews, "
            "and studio owners can view all client reviews from their dashboard."
        ), None, None, 'intent_answer'

    if intent == 'profile_help':
        return (
            "Your profile settings are in the dashboard. Users manage account details there, and studio owners can "
            "also update studio name, contact details, services, and cover image."
        ), None, None, 'intent_answer'

    if intent == 'dashboard_help':
        return dashboard_overview(user), None, None, 'intent_answer'

    if intent == 'studio_ops':
        return (
            "Studio owners can manage dashboard stats, portfolio uploads, bookings, earnings, reviews, and studio "
            "profile details from the studio panel."
        ), None, None, 'intent_answer'

    if intent == 'support':
        return (
            "If you need help, ask here about bookings, payments, reviews, dashboards, or setup. I will keep answers "
            "inside your role permissions."
        ), None, None, 'intent_answer'

    if intent == 'thanks':
        return "You are welcome. I can also explain any allowed page or workflow step by step.", None, None, 'intent_answer'

    return platform_overview(user), None, None, 'fallback'


def detect_policy_violation(text, role):
    if contains_any(text, SENSITIVE_PATTERNS):
        return 'sensitive_data'

    for intent, patterns in ROLE_RESTRICTED_PATTERNS.get(role, {}).items():
        if contains_any(text, patterns):
            return intent

    return None


def build_blocked_response(role, intent):
    target = INTENT_HINT.get(intent, 'restricted workflows')
    blocked_reason = f'{intent} is not allowed for role {role}.'
    policy_notice = build_policy_notice(role, intent, blocked=True)
    if intent == 'sensitive_data':
        response = (
            "I cannot share private account, payment, credential, document, or system-security information. "
            "Use the approved dashboard screens and permissions for that request."
        )
    else:
        response = (
            f"I cannot share {target} in this {ROLE_LABELS.get(role, role.lower())} account. "
            "Please use the correct role dashboard for that request."
        )
    return response, blocked_reason, policy_notice, 'guardrail'


def build_policy_notice(role, intent, blocked):
    if blocked:
        return f'Access boundary enforced: intent {intent} is not available for role {role}.'

    if role == 'ADMIN' and intent == 'admin_ops':
        return 'Safety mode active: validate evidence and record action rationale before administrative changes.'

    return f'Role-safe AI mode: answer constrained to {ROLE_LABELS.get(role, role.lower())} workflows only.'


def get_user_role(user):
    role = getattr(user, 'role', '')
    role = (role or '').upper()
    if role in ROLE_ALLOWED_INTENTS:
        return role
    return 'USER'


def classify_intent(text, role=None):
    role = role or 'USER'
    if contains_any(text, ['hello', 'hi', 'hey', 'greet', 'good morning', 'good evening']):
        return 'greeting'
    if contains_any(text, ['admin', 'moderation', 'manage users', 'manage studios']):
        return 'admin_ops'
    if contains_any(text, ['studio owner', 'studio dashboard', 'portfolio', 'earnings', 'payout', 'commission']):
        if role == 'USER':
            return 'studio_ops'
        if role == 'ADMIN' and contains_any(text, ['payout', 'commission']):
            return 'admin_ops'
        return 'studio_ops'
    if contains_any(text, ['what can you do', 'platform', 'functionality', 'features', 'how does it work']):
        return 'platform_overview'
    if contains_any(text, ['book', 'booking', 'reserve', 'reservation', 'studio booking']):
        return 'booking_help'
    if contains_any(text, ['price', 'cost', 'rate', 'charges', 'pricing', 'budget']):
        return 'pricing_help'
    if contains_any(text, ['payment', 'pay', 'refund', 'transaction', 'upi']):
        return 'payment_help'
    if contains_any(text, ['review', 'rating', 'feedback']):
        return 'review_help'
    if contains_any(text, ['profile', 'account', 'settings', 'preferences']):
        return 'profile_help'
    if contains_any(text, ['dashboard', 'menu', 'navigation', 'sidebar']):
        return 'dashboard_help'
    if contains_any(text, ['support', 'contact', 'help', 'issue', 'problem']):
        return 'support'
    if contains_any(text, ['thank', 'thanks', 'appreciate']):
        return 'thanks'
    return 'unknown'


def contains_any(text, phrases):
    return any(phrase in text for phrase in phrases)


def generate_role_safe_ai_answer(text, role):
    """Small local retrieval layer that behaves like role-constrained AI without external data leakage."""
    cards = ROLE_KNOWLEDGE_BASE.get(role, ROLE_KNOWLEDGE_BASE['USER'])
    tokens = Counter(re.findall(r'[a-z0-9]+', text))
    scored_cards = []

    for card in cards:
        score = 0
        for keyword in card['keywords']:
            keyword_tokens = keyword.split()
            if keyword in text:
                score += 4
            score += sum(tokens.get(token, 0) for token in keyword_tokens)
        if score:
            scored_cards.append((score, card))

    if not scored_cards:
        return None

    scored_cards.sort(key=lambda item: item[0], reverse=True)
    selected = [card for _, card in scored_cards[:2]]
    lines = [f"Role-safe AI summary for {ROLE_LABELS.get(role, role.lower())} workflows:"]
    for index, card in enumerate(selected, start=1):
        lines.append(f"{index}. {card['title']}: {card['answer']}")

    if role != 'ADMIN':
        lines.append("I cannot help with admin-only controls or private platform records from this role.")
    else:
        lines.append("Keep admin actions evidence-based and avoid exposing private credentials or documents in chat.")

    return "\n".join(lines)


def match_faq_answer(text, role):
    faqs = ChatbotFAQ.objects.filter(active=True).filter(Q(role_scope='ALL') | Q(role_scope=role))
    best_score = 0
    best_answer = None

    for faq in faqs:
        score = 0
        question = (faq.question or '').lower()
        keywords = [keyword.strip().lower() for keyword in (faq.keywords or '').split(',') if keyword.strip()]

        for keyword in keywords:
            if keyword and keyword in text:
                score += 3

        for word in re.findall(r'[a-z0-9]+', question):
            if word in text:
                score += 1

        if question and question in text:
            score += 5

        if score > best_score:
            best_score = score
            best_answer = faq.answer

    if best_score >= 2:
        return best_answer

    return None


def platform_overview(user):
    role = getattr(user, 'role', '').upper()

    if role == 'USER':
        return (
            "StudioSync lets users explore studios, compare locations and prices, book time slots, pay online, "
            "track bookings, leave reviews, and manage notifications and profile details from the user dashboard."
        )

    if role == 'STUDIO':
        return (
            "StudioSync helps studio owners manage portfolio images, studio profile details, services, bookings, "
            "earnings, and client reviews from the studio dashboard."
        )

    if role == 'ADMIN':
        return (
            "StudioSync admin tools cover user management, admin moderation, studio approval, booking oversight, "
            "and payment tracking from the admin panel."
        )

    return (
        "StudioSync is a photo studio booking platform. Users can explore studios, book sessions, pay online, and "
        "write reviews, while studio owners and admins manage listings, bookings, and operations from their dashboards."
    )


def dashboard_overview(user):
    role = getattr(user, 'role', '').upper()

    if role == 'USER':
        return (
            "User dashboard features include bookings, recommendations, reviews, payments, notifications, and profile "
            "settings. You can also browse studios from the explore page."
        )

    if role == 'STUDIO':
        return (
            "Studio dashboard features include studio stats, portfolio management, booking approvals, earnings, client "
            "reviews, and profile/service editing."
        )

    if role == 'ADMIN':
        return (
            "Admin dashboard features include user moderation, studio approval, booking monitoring, and payment "
            "tracking."
        )

    return platform_overview(user)


@login_required
def clear_chat_history(request):
    """Clear chat history for the current user."""
    try:
        ChatMessage.objects.filter(user=request.user).delete()
        return JsonResponse({'success': True, 'message': 'Chat history cleared'})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)
