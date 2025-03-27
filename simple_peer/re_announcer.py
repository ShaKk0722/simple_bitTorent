import logging
import time
import requests
from simple_peer.util import get_announce


logger = logging.getLogger('re_announcer')


def re_announce_announce(client_peer):
    """
    Used by the re_announcer to periodically announce
    the client_peer to the tracker to tell the tracker
    that the current peer is still active, not cleaned
    by the cleaner, also update some of the information
    of the client_peer
    :param client_peer: object peer to re-announce
    :return: (interval, peers)
    """
    client_peer.set_re_announce_event()
    response = requests.get(get_announce(client_peer.torrent), params=client_peer.get_params())
    if response.status_code == 200:
        interval = response.json()['interval']
        peers = response.json()['peers']
        # todo: replace the old peers with the new peers
        return interval, peers
    else:
        raise Exception("Failed to re-announce to tracker")


def re_announcer(interval, client_peer, peers, peers_lock):
    try:
        while True:
            time.sleep(interval)

            new_interval, new_peers = re_announce_announce(client_peer)

            interval = new_interval

            with peers_lock:
                peers.clear()
                peers.extend(new_peers)
    except Exception as e:
        logger.error(str(e))