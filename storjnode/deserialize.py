import re


class InvalidRelayNodeURL(Exception):
    pass


def relaynode(string):
    # adapted from http://stackoverflow.com/a/7160778/90351
    regex = re.compile(
        r'^(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+(?:[A-Z]{2,6}\.?|[A-Z0-9-]{2,}\.?)|'  # domain...
        r'localhost|'  # localhost...
        r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'  # ...or ip
        r'(?::\d+)?$'  # optional port
    , re.IGNORECASE)
    if not bool(regex.match(string)):
        raise InvalidRelayNodeURL()
    parts = string.split(":")
    host = parts[0]
    port = int(parts[1]) if len(parts) == 2 else 6667
    return host, port
