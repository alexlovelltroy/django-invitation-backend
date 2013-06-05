import signals

def logit(sender, **kwargs):
    print ("I got a signal from %s" % sender)
    print ("It told me all about %s" % kwargs)

signals.invitation_added.connect(logit)
signals.invitation_accepted.connect(logit)
