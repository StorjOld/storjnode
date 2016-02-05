from storjnode.network.messages import base


def create(btctxstore, wif, name):
    return base.create(btctxstore, wif, "signal", name)


def read(btctxstore, msg, name):
    print("In read")

    # not a valid message
    msg = base.read(btctxstore, msg)
    print(msg)
    if msg is None:
        print("11")
        return None

    # check token
    if msg.token != "signal":
        print("22")
        return None

    # check signal name
    if msg.body != name:
        print("33")
        return None

    return msg
