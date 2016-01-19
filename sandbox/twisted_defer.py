from twisted.internet import defer


def on_success(result):
    print("SUCCESS CALLED:", repr(result))


def on_error_handled(err):
    print("ERROR handled:", repr(err))
    # error is considered handled if error is not returned


def on_error_unhandled(err):
    print("ERROR unhandled:", repr(err))
    return err
    # error is considered unhandled if error is not returned


# handle error
print("Handle error")
d = defer.Deferred()
d.addCallback(on_success)
d.addErrback(on_error_handled)
d.errback(Exception("error"))

# handle error
print("Handle error")
d = defer.Deferred()
d.addCallback(on_success)
d.addErrback(on_error_unhandled)
d.errback(Exception("error"))
