from notifications.signals import notify
from .models import Profile
from .tasks import send_notification_email


def send_notification(sender, recipient, verb, description=None, target=None, level="info"):
    """
    Send an in-app notification and optionally an email notification based on user preferences.
    """
    # Send in-app notification
    notify.send(
        sender=sender,
        recipient=recipient,
        verb=verb,
        description=description,
        target=target,
        level=level,
    )

    # Check for email preference
    if hasattr(recipient, "profile"):
        # Default to False if preference not set, or True if you want default opt-in
        # Let's assume the preference key matches the 'verb' or a category
        # For simplicity, we'll check a generic 'email_notifications' setting for now
        # or specific keys.
        
        # We can map verbs to preference keys
        preference_key = verb.lower().replace(" ", "_")
        
        # Check if user has enabled this notification type
        # If the key doesn't exist, we can default to False (opt-in) or True (opt-out)
        # Let's default to True for now for "Group Message" and "Task Assigned"
        default_enabled = True
        
        if recipient.profile.email_notifications.get(preference_key, default_enabled):
            subject = f"Notification: {verb}"
            message = f"You have a new notification:\n\n{verb}\n{description or ''}"
            if target:
                message += f"\nTarget: {target}"
            
            # Enqueue email task
            send_notification_email.enqueue(
                subject=subject,
                message=message,
                recipient_list=[recipient.email],
            )
