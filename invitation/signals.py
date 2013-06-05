from django.dispatch import Signal


invitation_added = Signal(providing_args=['invitation'])

invitation_sent = Signal()

invitation_accepted = Signal(providing_args=['inviting_user', 'new_user'])
