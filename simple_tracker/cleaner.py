import time
import logging
from simple_tracker.util import SimpleTracker
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("cleaner")


def is_over_threshold(peer):
    if int(time.time()) - peer.last_announce_time >= SimpleTracker.THRESHOLD:
        return True
    return False


def cleaner(peers_db, peers_db_lock):
    try:
        while True:
            logger.info("Periodic cleaning...")
            time.sleep(SimpleTracker.CHECKING_TIME)
            # For each of the swarm
            with peers_db_lock:
                # iterate over the copy of dictionary
                for info_hash, swarm in list(peers_db.items()):
                    # For each of the peer in the swarm
                    for peer in swarm:
                        if is_over_threshold(peer):
                            # Exclude that peer from the swarm
                            logger.info('Clean ' + peer.peer_id)
                            peers_db[peer.info_hash] = [peer_mem for peer_mem in peers_db[peer.info_hash] if
                                                        peer_mem.peer_id != peer.peer_id]
                            # After excluding, if the swarm is empty
                            if not peers_db[peer.info_hash]:
                                # Delete that entry of the swarm
                                del peers_db[peer.info_hash]
    except Exception as e:
        logger.info(SimpleTracker.APP_NAME +': ' + str(e))