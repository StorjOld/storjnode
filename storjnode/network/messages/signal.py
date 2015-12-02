from storjnode.network.messages import base


def create(btctxstore, wif, name):
    return base.create(btctxstore, wif, "signal", name)


def read(btctxstore, msg, name):
    # FIXME raise exception if > max package size

    # not a valid message
    msg = base.read(btctxstore, msg)
    if msg is None:
        return None

    # check token
    if msg.token != "signal":
        return None

    # check signal name
    if msg.body != name:
        return None

    return msg
