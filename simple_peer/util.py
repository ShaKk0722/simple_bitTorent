import hashlib
import math
import os
import random
import string
import sys
import threading
import time
import bencodepy
import requests
from tqdm import tqdm


def create_pieces_hash(file_path, piece_length):
    hashes = []
    with open(file_path, 'rb') as f:
        piece = f.read(piece_length)
        while piece:
            hashes.append(hashlib.sha1(piece).digest())
            piece = f.read(piece_length)
    return b''.join(hashes)


def create_torrent(file_path, ip, port, piece_length, destination_directory):
    file_size = os.path.getsize(file_path)
    file_name = os.path.basename(file_path)
    piece_hashes = create_pieces_hash(file_path, piece_length)

    info = {
        'name': file_name,
        'length': file_size,
        'piece length': piece_length,
        'pieces': piece_hashes
    }

    torrent_dict = {
        'announce': f'http://{ip}:{port}/announce',
        'created by': SimpleClient.APP_NAME,
        'creation date': int(time.time()),
        'version': SimpleClient.VERSION,
        'info': info
    }

    torrent_data = bencodepy.encode(torrent_dict)

    torrent_file = file_name + '.torrent'
    torrent_file_path = os.path.join(destination_directory, torrent_file)
    with open(torrent_file_path, 'wb') as f:
        f.write(torrent_data)


def get_torrent_dic_from_torrent_dic_bytes(torrent_dict_bytes):
    torrent_dic = {
        'announce': torrent_dict_bytes[b'announce'].decode('utf-8'),
        'created by': torrent_dict_bytes[b'created by'].decode('utf-8'),
        'creation date': torrent_dict_bytes[b'creation date'],
        'version': torrent_dict_bytes[b'version'].decode('utf-8'),
        'info': {
            'name': torrent_dict_bytes[b'info'][b'name'].decode('utf-8'),
            'length': torrent_dict_bytes[b'info'][b'length'],
            'piece length': torrent_dict_bytes[b'info'][b'piece length'],
            'pieces': torrent_dict_bytes[b'info'][b'pieces']
        }
    }
    return torrent_dic


def generate_peer_id(client_prefix='PC000'):
    """
    Generates a valid peer_id for BitTorrent clients. The peer_id is 20 bytes long.
    The first 5 characters are the client's name prefix, and the next 15 are random characters.

    Args:
        client_prefix (str): The prefix that represents the client name (default is '-PC000').

    Returns:
        str: A 20-character peer_id string.
    """
    # Ensure the prefix is 5 characters long
    if len(client_prefix) != 5:
        raise ValueError("Prefix must be exactly 5 characters long")
    # Generate 15 random alphanumeric characters
    random_suffix = ''.join(random.choices(string.ascii_letters + string.digits, k=15))
    # Combine the prefix and the random suffix
    return client_prefix + random_suffix


def create_file(file, length):
    """
    Create a file with a specific total size, initialized with zero bytes.
    This simulates the space allocated for the entire file.
    :param file: The path to file to create.
    :param length: The total length of the file.
    """
    # todo: when the size of the file is large
    # todo: we can't load 15 Gb into the RAM
    # todo: we will write in chunk until written = length
    chunk_size = 1024 * 1024  # 1 MB per write
    written = 0
    with open(file, 'wb') as f:
        while written < length:
            to_write = min(chunk_size, length - written)
            f.write(b'\0' * to_write)
            written += to_write


def get_info_hash(file):
    """
    Generates the info hash from the torrent file.
    Used for identifying the torrent's swarm
    :param file: the torrent file
    :return: info_hash of the torrent
    """
    with open(file, 'rb') as f:
        data = f.read()
        torrent_dic_bytes = bencodepy.decode(data)
        torrent_dic = get_torrent_dic_from_torrent_dic_bytes(torrent_dic_bytes)
        info = torrent_dic['info']
        info_hash = hashlib.sha1(bencodepy.encode(info)).digest()
    return info_hash


def get_torrent_dic(torrent):
    """
    Decode the torrent raw file into the torrent dictionary
    :param torrent: torrent file of the file
    :return: torrent dictionary
    """
    with open(torrent, 'rb') as f:
        data = f.read()
        torrent_dic_bytes = bencodepy.decode(data)
        torrent_dic = get_torrent_dic_from_torrent_dic_bytes(torrent_dic_bytes)
        return torrent_dic


def get_piece_length(file):
    torrent_dic = get_torrent_dic(file)
    return torrent_dic['info']['piece length']


def get_file_length(torrent):
    """
    Calculate the length of the file in bytes
    :param torrent: the torrent of the file
    :return: length of the file extracted from the torrent
    """
    torrent_dic = get_torrent_dic(torrent)
    return torrent_dic['info']['length']


def get_piece_number(file):
    length = get_file_length(file)
    piece_length = get_piece_length(file)
    return math.ceil(length / piece_length)


def get_announce(file):
    torrent_dic = get_torrent_dic(file)
    return torrent_dic['announce']


def get_piece_hash(piece_index, torrent):
    torrent_dic = get_torrent_dic(torrent)
    # byte object
    pieces_hash = torrent_dic['info']['pieces']
    # calculate the index (byte) of the piece hash
    start = 20 * piece_index
    return pieces_hash[start:start + 20]


def create_piece_hash(piece_data):
    """
    Calculates the piece hash of a piece_data.
    :param piece_data: piece_data to create piece hash
    :return: the hash of the piece data
    """
    return hashlib.sha1(piece_data).digest()


def get_interest_piece_index(interest_request):
    return int(interest_request.split()[1])


def verify_piece(piece_data, piece_index, torrent):
    calculated_piece_hash = create_piece_hash(piece_data)
    torrent_piece_hash = get_piece_hash(piece_index, torrent)
    return calculated_piece_hash == torrent_piece_hash


def write_piece(piece_data, piece_index, torrent, file):
    piece_length = get_piece_length(torrent)
    offset = piece_index * piece_length
    with open(file, 'r+b') as f:
        f.seek(offset)
        f.write(piece_data)
        
        
def recv_exact_bytes(socket, expected_bytes):
    """
    Receives exactly the specified number of bytes from the socket.

    Args:
        socket: The socket object to receive data from.
        expected_bytes: The exact number of bytes to receive.

    Returns:
        A bytes object containing exactly `expected_bytes` bytes.

    Raises:
        ValueError: If the connection is closed before receiving the expected amount of data.
    """
    data = b''
    # len of data is still less than expected_bytes
    # continue to read as much as possible, expected_bytes - len(data)
    while len(data) < expected_bytes:
        chunk = socket.recv(expected_bytes - len(data))
        if not chunk:
            raise ValueError("Connection closed before receiving expected data")
        data += chunk
    return data


def leecher_init(torrent, file, ip, port):
    peer = Peer(torrent, file, ip, port)
    peer_pieces_tracking = {i: 'UNAVAILABLE' for i in range(get_piece_number(peer.torrent))}
    peer_lock = threading.Lock()
    peer_pieces_tracking_lock = threading.Lock()
    peer.init_leecher()
    return peer, peer_lock, peer_pieces_tracking, peer_pieces_tracking_lock


def seeder_init(torrent, file, ip, port):
    peer = Peer(torrent, file, ip, port)
    peer_pieces_tracking = {i: 'AVAILABLE' for i in range(get_piece_number(peer.torrent))}
    peer_lock = threading.Lock()
    peer_pieces_tracking_lock = threading.Lock()
    peer.init_seeder()
    return peer, peer_lock, peer_pieces_tracking, peer_pieces_tracking_lock


def started_announce(client_peer):
    """
    In the join command, first announce the tracker to tell
    the tracker that this peer will join the swarm.
    Also getting a list of other peers, who are in the swarm
    :param client_peer: the Peer object represent a peer
    :return: (interval, peers)
    """
    client_peer.set_started_event()
    response = requests.get(get_announce(client_peer.torrent), params=client_peer.get_params())
    if response.status_code == 200:
        interval = response.json()['interval']
        peers = response.json()['peers']
        return interval, peers
    else:
        raise Exception("Failed to started announce to tracker.")


def stop_announce(client_peer):
    """
    Tell the tracker that this peer will be out of the swarm.
    :param client_peer: object represents client peer
    :return: None
    :exception Exception: Failed to stopped announce to tracker.
    """
    client_peer.set_stopped_event()
    response = requests.get(get_announce(client_peer.torrent), params=client_peer.get_params())
    if response.status_code != 200:
        raise Exception("Failed to stopped announce to tracker.")


def is_download_completed(peer):
    return peer.left == 0


# def progress_bar(left, total_pieces, bar_length=40):
#     # Calculate the download progress
#     downloaded_pieces = total_pieces - left
#     progress = downloaded_pieces / total_pieces
#
#     # Create the bar, percentage of bar
#     block = int(round(bar_length * progress))
#     bar = "#" * block + "-" * (bar_length - block)
#
#     # Display the bar with the percentage
#     sys.stdout.write(f"\rDownloading: [{bar}] {progress * 100:.2f}%")
#     sys.stdout.flush()


# def progress_display(peer):
#     # skip by seeder because left = 0
#     while peer.left >= 0:
#         # print(peer.left)
#         time.sleep(0.1)
#         # Display the progress bar
#         progress_bar(peer.left, get_piece_number(peer.torrent))
#         if peer.left == 0:
#             return


def init_progress_bar(client_peer):
    total_size = get_file_length(client_peer.torrent)
    piece_length = get_piece_length(client_peer.torrent)
    with tqdm(total=total_size, unit='B', unit_scale=True, desc='Downloading') as progress_bar:
        downloaded_bytes = 0  # Track downloaded bytes
        while client_peer.left > 0:
            # Calculate how many bytes have been downloaded since the last update
            new_downloaded_bytes = min(client_peer.downloaded * piece_length, total_size)
            bytes_downloaded_since_last_update = new_downloaded_bytes - downloaded_bytes

            # Update the progress bar with the number of bytes downloaded since the last update
            progress_bar.update(bytes_downloaded_since_last_update)

            # Update downloaded_bytes to the current downloaded bytes
            downloaded_bytes = new_downloaded_bytes

            # Optional: to avoid too frequent updates, you can add a small sleep here
            # time.sleep(0.1)

        # After the download is complete, make sure the progress bar reaches 100%
        if client_peer.left == 0:
            progress_bar.update(total_size - downloaded_bytes)


class Peer:
    def __init__(self, torrent, file, ip, port):
        self.torrent = torrent
        self.file = file
        self.info_hash = get_info_hash(torrent)
        self.peer_id = generate_peer_id()
        self.peer_ip = ip
        self.peer_port = port
        self.uploaded = 0
        self.downloaded = 0
        self.left = 0
        self.event = EVENT_LIST[0]
        self.lock = threading.Lock()


    def get_params(self):
        params = {
            'info_hash': self.info_hash,
            'peer_id': self.peer_id,
            'peer_ip': self.peer_ip,
            'peer_port': self.peer_port,
            'uploaded': self.uploaded,
            'downloaded': self.downloaded,
            'left': self.left,
            'event': self.event
        }
        return params


    def init_seeder(self):
        with self.lock:
            self.uploaded = 0
            self.downloaded = 0
            self.left = 0
            self.event = EVENT_LIST[0]


    def init_leecher(self):
        with self.lock:
            self.uploaded = 0
            self.downloaded = 0
            self.left = get_piece_number(self.torrent)
            self.event = EVENT_LIST[0]


    def set_started_event(self):
        with self.lock:
            self.event = EVENT_LIST[0]


    def set_stopped_event(self):
        with self.lock:
            self.event = EVENT_LIST[1]


    def set_re_announce_event(self):
        with self.lock:
            self.event = EVENT_LIST[2]


    def update_peer_available(self):
        with self.lock:
            self.downloaded = self.downloaded + 1
            self.left = self.left - 1


    def update_peer_uploaded(self):
        with self.lock:
            self.uploaded = self.uploaded + 1


class SimpleClient:
    APP_NAME = 'Simple Bittorrent CLI'
    VERSION = '1.0.0'
    TALKER_CHECKING = 40
    HAVING_REQUEST_TIME = 10


EVENT_LIST = [
    'STARTED',      # 0
    'STOPPED',      # 1
    'RE_ANNOUNCE'   # 2
]
