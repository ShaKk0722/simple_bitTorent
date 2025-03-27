import json
import logging
import socket
import struct
import threading
import time
from simple_peer.config import INFO
from simple_peer.util import get_piece_number, get_piece_length, verify_piece, write_piece, is_download_completed, SimpleClient, \
    recv_exact_bytes, get_file_length


logger = logging.getLogger("requester")


def talker(client_peer, server_peers, server_peers_lock, peer_pieces_tracking, client_peer_lock, peer_pieces_tracking_lock):
    """
    Generate multiple threads to concurrently request pieces
    from the server peer.
    :param client_peer: object representing the client peer
    :param server_peers: list of dictionary of server peers
    :param server_peers_lock: the lock for changing server_peers
    :param peer_pieces_tracking: dictionary of pieces tracking of the client peer
    :param client_peer_lock: the lock for changing the client_peer
    :param peer_pieces_tracking_lock: the lock for changing the peer_pieces_tracking
    :return: None
    """
    connected_server_peers = set([])
    connected_server_peers_lock = threading.Lock()

    while not is_download_completed(client_peer):
        with server_peers_lock:
            with connected_server_peers_lock:
                for server_peer in server_peers:
                    if (server_peer['peer_id'] != client_peer.peer_id and
                        server_peer['peer_id'] not in connected_server_peers):

                        connected_server_peers.add(server_peer['peer_id'])

                        requester_thread = threading.Thread(target=requester, args=(client_peer,
                                                                            server_peer,
                                                                            peer_pieces_tracking,
                                                                            peer_pieces_tracking_lock,
                                                                            client_peer_lock,
                                                                            connected_server_peers,
                                                                            connected_server_peers_lock,
                                                                            server_peers,
                                                                            server_peers_lock),
                                                            daemon=True)

                        requester_thread.start()
        time.sleep(SimpleClient.TALKER_CHECKING)


def requester(client_peer, server_peer, peer_pieces_tracking, peer_pieces_tracking_lock,
              client_peer_lock, connected_server_peers, connected_server_peers_lock, server_peers, server_peers_lock):
    """
    The function run by the thread to create the connection to the server peer.
    Call by create_connections_to_server_peers
    :param client_peer: object represents the client peer
    :param server_peer: dictionary represents the server peer
    :param peer_pieces_tracking: dictionary of pieces tracking of the client peer
    :param peer_pieces_tracking_lock: the lock for changing the peer_pieces_tracking
    :param client_peer_lock: the lock for changing the client_peer
    :param connected_server_peers_lock: set of connected server peers
    :param connected_server_peers: the lock for changing the connected_server_peers
    :param server_peers: list of dictionary represents the server peers
    :param server_peers_lock: lock for changing the server_peers
    :return: None
    """
    # todo: thread to connect to the server peer
    with connected_server_peers_lock:
        connected_server_peers.add(server_peer['peer_id'])

    client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        client_socket.connect((server_peer['peer_ip'], server_peer['peer_port']))

        requester_having_interests(client_peer, client_socket, peer_pieces_tracking, client_peer_lock,
                                   peer_pieces_tracking_lock, server_peer)

        requester_done(client_socket)

        with connected_server_peers_lock:
            connected_server_peers.remove(server_peer['peer_id'])
    except Exception as e:
        with connected_server_peers_lock:
            if server_peer['peer_id'] in connected_server_peers:
                connected_server_peers.remove(server_peer['peer_id'])

        with server_peers_lock:
            for server_peer_mem in server_peers:
                if server_peer['peer_id'] == server_peer_mem['peer_id']:
                    server_peers.remove(server_peer_mem)


        if INFO:
            logger.info(str(e))
    finally:
        client_socket.close()


def update_peer_pieces_tracking_available(peer_pieces_tracking, peer_pieces_tracking_lock, piece_index):
    # todo, lock the peer_pieces_tracking and update the piece_index
    peer_pieces_tracking_lock.acquire()
    peer_pieces_tracking[piece_index] = 'AVAILABLE'
    peer_pieces_tracking_lock.release()


def update_peer_pieces_tracking_downloading(peer_pieces_tracking, peer_pieces_tracking_lock, piece_index):
    peer_pieces_tracking_lock.acquire()
    peer_pieces_tracking[piece_index] = 'DOWNLOADING'
    peer_pieces_tracking_lock.release()


def update_peer_pieces_tracking_unavailable(peer_pieces_tracking, peer_pieces_tracking_lock, piece_index):
    peer_pieces_tracking_lock.acquire()
    peer_pieces_tracking[piece_index] = 'UNAVAILABLE'
    peer_pieces_tracking_lock.release()


def requester_having_accumulator(peer_client_socket):
    # print('Starting handling full json')
    # First, receive the message length (assuming a 4-byte integer length header)
    length_header = peer_client_socket.recv(4)  # Read the first 4 bytes for the length
    if not length_header:
        # If no length header received, the connection has been closed
        raise ValueError("Connection closed unexpectedly")

    # Unpack the length from the header
    message_length = struct.unpack('!I', length_header)[0]  # Big-endian unsigned int

    full_data = recv_exact_bytes(peer_client_socket, message_length)

    # Once we have the full message, attempt to decode and parse it
    try:
        json_data = full_data.decode('utf-8')  # Decode bytes to string
        parsed_json = json.loads(json_data)  # Parse the string into a JSON object
        # print('Finishing handling full json')
        return parsed_json  # Return the parsed JSON object if successful
    except (UnicodeDecodeError, json.JSONDecodeError):
        # If decoding or JSON parsing fails, continue to receive data
        if INFO:
            logger.info('Error parsing JSON, waiting for more data...')

def requester_having(client_socket):
    """
    Send the 'HAVING' request using client_socket,
    request for the dictionary of available pieces
    of the server peer
    :param client_socket: socket used to send
    :return: dictionary of available pieces
    """
    # print('Sending HAVING request')
    client_socket.send('HAVING\n'.encode('utf-8'))
    server_peer_pieces_tracking = requester_having_accumulator(client_socket)
    # print('Receiving HAVING response')
    # todo: in the form as {'0': 'AVAILABLE'}
    # todo: convert back to indexable form
    server_peer_pieces_tracking = {int(k) : v for k, v in server_peer_pieces_tracking.items()}
    return server_peer_pieces_tracking


def requester_interest(peer_client_socket, client_peer, client_peer_lock, peer_pieces_tracking, peer_pieces_tracking_lock, i, server_peer):
    try:
        # set DOWNLOADING on this piece index
        update_peer_pieces_tracking_downloading(peer_pieces_tracking, peer_pieces_tracking_lock, i)
        interest_message = f'INTEREST {i}\n'
        peer_client_socket.send(interest_message.encode('utf-8'))
        # print(f'Sending INTEREST request {i}')
        if i == get_piece_number(client_peer.torrent) - 1:
            # if it is the last piece index
            # calculate the last piece length
            last_piece_length = get_file_length(client_peer.torrent) - (
                        (get_piece_number(client_peer.torrent) - 1) * get_piece_length(client_peer.torrent))
            piece_data = recv_exact_bytes(peer_client_socket, last_piece_length)
        else:
            piece_data = recv_exact_bytes(peer_client_socket, get_piece_length(client_peer.torrent))

        if verify_piece(piece_data, i, client_peer.torrent):
            # todo: write piece_data to the file
            write_piece(piece_data, i, client_peer.torrent, client_peer.file)
            # todo: update the piece_pieces_tracking
            client_peer.update_peer_available()
            update_peer_pieces_tracking_available(peer_pieces_tracking, peer_pieces_tracking_lock, i)
            server_ip, server_port = peer_client_socket.getpeername()
            if INFO:
                logger.info(f'Downloaded piece [{i}] from [{server_ip}][{server_port}]')
        else:
            if INFO:
                logger.info(f'Piece [{i}] is wrong')
            update_peer_pieces_tracking_unavailable(peer_pieces_tracking, peer_pieces_tracking_lock, i)
    except Exception as e:
        update_peer_pieces_tracking_unavailable(peer_pieces_tracking, peer_pieces_tracking_lock, i)
        raise


def requester_interests(client_peer, peer_client_socket, peer_pieces_tracking, server_peer_pieces_tracking, client_peer_lock, peer_pieces_tracking_lock, server_peer):
        for i in range(get_piece_number(client_peer.torrent)):
            if server_peer_pieces_tracking[i] == 'AVAILABLE' and peer_pieces_tracking[i] == 'UNAVAILABLE':
                update_peer_pieces_tracking_downloading(peer_pieces_tracking, peer_pieces_tracking_lock, i)
                requester_interest(peer_client_socket, client_peer, client_peer_lock, peer_pieces_tracking, peer_pieces_tracking_lock, i, server_peer)


def requester_having_interests(client_peer, peer_client_socket, peer_pieces_tracking, client_peer_lock, peer_pieces_tracking_lock, server_peer):
    while not is_download_completed(client_peer):

        time.sleep(SimpleClient.HAVING_REQUEST_TIME)

        server_peer_pieces_tracking = requester_having(peer_client_socket)

        requester_interests(client_peer, peer_client_socket, peer_pieces_tracking, server_peer_pieces_tracking, client_peer_lock, peer_pieces_tracking_lock, server_peer)


def requester_done(peer_client_socket):
    done_message = 'DONE\n'
    peer_client_socket.send(done_message.encode('utf-8'))
    done_message_received = peer_client_socket.recv(1024).decode('utf-8')
    if done_message_received == 'DONE_OK':
        peer_client_socket.close()