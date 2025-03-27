import time
from flask import request


def announce_parse_request():
    """
    Parse the HTTP request from peers
    :return: Object represent a peer in the tracker server
    """
    return Peer(request.args.get('info_hash', type=str),
                request.args.get('peer_id', type=str),
                request.args.get('peer_ip', type=str),
                request.args.get('peer_port', type=int),
                request.args.get('uploaded', type=int),
                request.args.get('downloaded', type=int),
                request.args.get('left', type=int),
                request.args.get('event', type=str))


def announce_handler_lack_info(client_peer):
    if ((not client_peer.info_hash) or
            (not client_peer.peer_id) or
            (not client_peer.peer_ip) or
            (client_peer.peer_port <= 0)):
        return "Announce unsuccessfully", 400


def announce_handler_stopped_event(peers_db, peers_db_lock, client_peer):
    with peers_db_lock:
        peers_db[client_peer.info_hash] = [peer_mem for peer_mem in peers_db[client_peer.info_hash] if peer_mem.peer_id != client_peer.peer_id]
        if not peers_db[client_peer.info_hash]:
            del peers_db[client_peer.info_hash]


def announce_handler_started_event(peers_db, peers_db_lock, client_peer):
    with peers_db_lock:
        if client_peer.info_hash not in peers_db:
            # Create an empty list of Peer object
            peers_db[client_peer.info_hash] = []
        peers_db[client_peer.info_hash].append(client_peer)


def announce_handler_re_announce_event(peers_db, peers_db_lock, client_peer):
    with peers_db_lock:
        # case when cleaner cleans the only peer in the
        # swarm, delete the info_hash entry in the database
        if client_peer.info_hash not in peers_db:
            with peers_db_lock:
                peers_db[client_peer.info_hash] = []
                peers_db[client_peer.info_hash].append(client_peer)
                return
        for peer_mem in peers_db[client_peer.info_hash]:
            if peer_mem.peer_id == client_peer.peer_id:
                # update the peer information, along with the
                # last_announce_time, return a refreshed
                # list of peer
                peer_mem.update(client_peer)
                return
        # in the case, tracker don't find any peer_mem
        # in the swarm, tracker's cleaner deleted it out
        # of the peer, but there is still the swarm's entry
        # re-append the client_peer
        peers_db[client_peer.info_hash].append(client_peer)


def announce_handler_swarm_response(client_peer, peers_db, peers_db_lock):
    with peers_db_lock:
        swarm = peers_db.get(client_peer.info_hash, [])
    # Convert to a list of dictionary
    swarm = [peer_mem.to_dict() for peer_mem in swarm]
    swarm_response = {
        'interval': SimpleTracker.INTERVAL,
        'peers': swarm
    }
    return swarm_response


class Peer:
    def __init__(self, info_hash, peer_id, peer_ip, peer_port, uploaded, downloaded, left, event):
        self.info_hash = info_hash
        self.peer_id = peer_id
        self.peer_ip = peer_ip
        self.peer_port = peer_port
        self.uploaded = uploaded
        self.downloaded = downloaded
        self.left = left
        self.event = event
        # Represent the last announce time
        # Used for scheduled clean-up service
        self.last_announce_time = int(time.time())


    def update(self, peer):
        self.info_hash = peer.info_hash
        self.peer_id = peer.peer_id
        self.peer_ip = peer.peer_ip
        self.peer_port = peer.peer_port
        self.uploaded = peer.uploaded
        self.downloaded = peer.downloaded
        self.left = peer.left
        self.event = peer.event
        # Update the last_announce_time
        self.last_announce_time = int(time.time())


    def to_dict(self):
        return {
            'info_hash': self.info_hash,
            'peer_id': self.peer_id,
            'peer_ip': self.peer_ip,
            'peer_port': self.peer_port,
            'uploaded': self.uploaded,
            'downloaded': self.downloaded,
            'left': self.left,
            'event': self.event
        }


class SimpleTracker:
    APP_NAME= 'Simple Bittorrent Tracker'
    VERSION='1.0.0'
    # 1 minutes
    INTERVAL=1*60
    # for every 10 seconds
    # running the clean-up
    CHECKING_TIME=10
    THRESHOLD=1*60+30
    EVENT_LIST = ['STARTED',        # 0
                  'STOPPED',        # 1
                  'RE_ANNOUNCE']    # 2