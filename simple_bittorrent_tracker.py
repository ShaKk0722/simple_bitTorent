from simple_tracker.cleaner import cleaner
from simple_tracker.util import SimpleTracker, announce_parse_request, announce_handler_lack_info, \
    announce_handler_stopped_event, announce_handler_started_event, announce_handler_re_announce_event, \
    announce_handler_swarm_response
from flask import Flask, jsonify
import threading
import logging

simple_bittorrent_tracker = Flask(__name__)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("announce")


# DICTIONARY
#   {
#       'info_hash': [list of peers (object)],
#       'info_hash': [list of peers (object)]
#   }
peers_db = {}
peers_db_lock = threading.Lock()

@simple_bittorrent_tracker.route('/', methods=['GET'])
def test():
    return 'Hello', 200


@simple_bittorrent_tracker.route('/announce', methods=['GET'])
def announce():
    peer = announce_parse_request()

    announce_handler_lack_info(peer)

    # STOPPED event
    if peer.event == SimpleTracker.EVENT_LIST[1]:
        announce_handler_stopped_event(peers_db, peers_db_lock, peer)
        return "Peer stopped", 200

    # STARTED event
    elif peer.event == SimpleTracker.EVENT_LIST[0]:
        announce_handler_started_event(peers_db, peers_db_lock, peer)

    # RE_ANNOUNCE event
    elif peer.event == SimpleTracker.EVENT_LIST[2]:
        announce_handler_re_announce_event(peers_db, peers_db_lock, peer)

    # response the swarms
    return jsonify(announce_handler_swarm_response(peer, peers_db, peers_db_lock)), 200


# Start the Flask server with threaded support
def run():
    simple_bittorrent_tracker.run(host='0.0.0.0', port=8080, threaded=True)


# Run the Flask server in a new thread
if __name__ == '__main__':
    server_thread = threading.Thread(target=run)
    server_thread.start()
    cleaner_thread = threading.Thread(target=cleaner, args=(peers_db, peers_db_lock), daemon=True)
    cleaner_thread.start()
