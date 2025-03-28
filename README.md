
# Simple BitTorrent Application

This is a simple implementation of a BitTorrent-like system consisting of a **Tracker** and **Peers** (Seeder/Leecher). The tracker manages file sharing metadata, while peers upload or download files.

---

## Features
- **Tracker**: Keeps track of files, peers, and availability.
- **Peer (Seeder/Leecher)**: Downloads or uploads pieces of files to/from other peers.
- **Provide**: multi-threaded application, each of peer can serer as a server and 

---

## Prerequisites
- Python 3.7 or above
- pip install -r requirements.txt
- Socket programming basics

---

## Components

### 1. **Tracker**
The tracker acts as the central server, managing peer information and file metadata.

#### Tracker Source Code
```python
# simple_bittorrent_tracker.py
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
    simple_bittorrent_tracker.run(host='0.0.0.0', port=80, threaded=True)


# Run the Flask server in a new thread
if __name__ == '__main__':
    server_thread = threading.Thread(target=run)
    server_thread.start()
    cleaner_thread = threading.Thread(target=cleaner, args=(peers_db, peers_db_lock), daemon=True)
    cleaner_thread.start()
```

---

### 2. **Peer (Seeder/Leecher)**
Peers upload and download files by communicating with the tracker and other peers.

#### Peer Source Code
```python
import threading
import click
import pprint
import logging
from simple_peer.config import DEBUG, INFO, DEMO
from simple_peer.re_announcer import re_announcer
from simple_peer.talker import talker
from simple_peer.listener import listener
from simple_peer.util import create_torrent, create_file, get_torrent_dic, get_file_length, \
    started_announce, is_download_completed, SimpleClient, stop_announce, leecher_init, seeder_init, \
    init_progress_bar


logger = logging.getLogger(SimpleClient.APP_NAME)


#configure logging
if DEBUG:
    logging.basicConfig(level=logging.DEBUG)
if INFO:
    logging.basicConfig(level=logging.INFO)
if DEMO:
    logging.basicConfig(level=logging.ERROR)


@click.group()
def cli():
    pass


@cli.command()
@click.option('-f', '--file', required=True, type=str, help="Name of file")
@click.option('-ip', '--ip', required=True, type=str, help="IP address of tracker")
@click.option('-p', '--port', required=True, type=int, help="Port of tracker")
@click.option('-pl', '--piece-length', required=False, default = 512 * 1024, type=int, help="Length of piece (byte), default to be 512KB")
@click.option('-d', '--destination', required=True, type=str, help="Destination directory")
def torrent(file, ip, port, piece_length, destination):
    try:
        create_torrent(file, ip, port, piece_length, destination)
        click.echo(f'Creating torrent from file {file}')
        click.echo(f'Saving torrent to {destination}')
    except Exception as e:
        logger.error(str(e))


@cli.command()
@click.option('-t', '--torrent', required=True, type=str, help="Name of torrent")
def meta(torrent):
    try:
        torrent_dic = get_torrent_dic(torrent)
        torrent_dic['info']['pieces'] = '***'
        pprint.pprint(torrent_dic)
    except Exception as e:
        logger.error(str(e))


@cli.command()
@click.option('-t', '--torrent', required=True, type=str, help="Name of torrent")
@click.option('-f', '--file', required=True, type=str, help="Name of file")
@click.option('-ip', '--ip', required=True, type=str, help="IP address of peer")
@click.option('-p', '--port', required=True, type=int, help="Port of the peer")
def join(torrent, file, ip, port):
    try:
        (peer,
         peer_lock,
         peer_pieces_tracking,
         peer_pieces_tracking_lock) = leecher_init(torrent, file, ip, port)


        create_file(peer.file, get_file_length(peer.torrent))

        interval, peers = started_announce(peer)
        peers_lock = threading.Lock()
        if DEBUG or INFO:
            pprint.pprint(peers)

        # re_announcer
        re_announcer_thread = threading.Thread(target=re_announcer, args=(interval, peer, peers, peers_lock), daemon=True)
        re_announcer_thread.start()


        # talker
        talker_thread = threading.Thread(target=talker, args=(peer, peers, peers_lock, peer_pieces_tracking, peer_lock, peer_pieces_tracking_lock), daemon=True)
        talker_thread.start()


        # listener
        listener_thread = threading.Thread(target=listener, args=(peer, peer_pieces_tracking, peer_lock), daemon=True)
        listener_thread.start()

        # progress bar
        if DEMO:
            init_progress_bar(peer)


        while True:
            if is_download_completed(peer):
                print('')
                is_continue_to_seed = input('Download successfully, continue to seed? (yes/no): ')
                if is_continue_to_seed == 'no':
                    stop_announce(peer)
                    # kill re_announcer
                    # listener will be killed
                    # handler will be killed
                    return
                else:
                    click.echo('Seeding...')
    except Exception as e:
        logger.error(str(e))


@cli.command()
@click.option('-t', '--torrent', required=True, type=str, help="Name of torrent")
@click.option('-f', '--file', required=True, type=str, help="Name of file saved")
@click.option('-ip', '--ip', required=True, type=str, help="IP address of peer")
@click.option('-p', '--port', required=True, type=int, help="Port of the peer")
def seed(torrent, file, ip, port):
    try:
        (peer,
         peer_lock,
         peer_pieces_tracking,
         peer_pieces_tracking_lock) = seeder_init(torrent, file, ip, port)


        interval, peers = started_announce(peer)
        peers_lock = threading.Lock()
        if DEBUG or INFO:
            pprint.pprint(peers)


        # re_announcer
        re_announcer_thread = threading.Thread(target=re_announcer, args=(interval, peer, peers, peers_lock), daemon=True)
        re_announcer_thread.start()


        # listener
        listener_thread = threading.Thread(target=listener, args=(peer, peer_pieces_tracking, peer_lock), daemon=True)
        listener_thread.start()


        while True:
            if is_download_completed(peer):
                print('')
                is_continue_to_seed = input('Continue to seed? (yes/no): ')
                if is_continue_to_seed == 'no':
                    stop_announce(peer)
                    # kill re_announcer
                    # kill listener
                    # kill handler
                    return
                else:
                    print('Seeding...')
    except Exception as e:
        logger.error(str(e))


if __name__ == '__main__':
    cli()```
---

## How to Run

### Step 1: Run the Tracker
Start the tracker to listen for peer announcements.
```bash
python simple_bittorrent_tracker.py
```

### Step 2: Start Peers
Run multiple instances of the peer script. Some peers act as seeders, while others act as leechers with specific command like [torrent], [seed], [join]
```bash
python simple_bittorrent_peer.py
```


## Notes
- This implementation is a simplified model and does not handle:
  - Complex peer communication
  - Advanced error handling
  - Authentication and authorisation

---
