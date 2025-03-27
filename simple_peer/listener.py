import json
import logging
import socket
import struct
import threading

from simple_peer.config import INFO
from simple_peer.util import get_interest_piece_index, get_piece_length


listener_logger = logging.getLogger('listener')
handler_logger = logging.getLogger('handler')


def listener(server_peer, peer_pieces_tracking, server_peer_lock):
    """
    The central server thread to generate each thread for handling
    each of the connections from the client peer
    :param server_peer: object representing the server peer
    :param peer_pieces_tracking: dictionary represent peer pieces tracking
    :param server_peer_lock: lock for changing the server peer
    :return: None
    """
    # todo: a central thread that accepts the connection from client peers
    try:
        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_socket.bind((server_peer.peer_ip, server_peer.peer_port))

        server_socket.listen(10)

        while True:
            server_client_socket, addr = server_socket.accept()
            handler_thread = threading.Thread(target=handler, args=(server_peer, server_client_socket, peer_pieces_tracking, server_peer_lock), daemon=True)
            handler_thread.start()
    except Exception as e:
        listener_logger.error(str(e))


def handler(server_peer, server_client_socket, peer_pieces_tracking, server_peer_lock):
    """
    Run by thread created by handle_connections_from_client_peers
    to handle a connection from the client peer
    :param server_peer: object represents the server peer
    :param server_client_socket: socket to send and receive message from client peer
    :param peer_pieces_tracking: dictionary represents peer pieces tracking
    :param server_peer_lock: lock to change the server peer
    :return: None
    """
    # todo: thread that instantly handle requests from a peer
    try:
        buffer = ""
        while True:
            # Receive data and append to buffer
            data = server_client_socket.recv(1024).decode('utf-8')
            if not data:
                break  # Client closed connection

            buffer += data

            # Process all complete messages in the buffer
            while "\n" in buffer:
                # Split the buffer on the newline delimiter
                request_message, buffer = buffer.split("\n", 1)

                request_type = handler_request_type(request_message)
                if request_type == 'DONE':
                    handler_done(server_client_socket)
                    return
                elif request_type == 'HAVING':
                    handler_having(server_client_socket, peer_pieces_tracking)
                elif request_type == 'INTEREST':
                    handler_interest(server_peer, server_client_socket, request_message, server_peer_lock)
    except Exception as e:
        if INFO:
            handler_logger.info(str(e))
    finally:
        server_client_socket.close()



def handler_request_type(request):
    if request == 'HAVING':
        return 'HAVING'
    elif request == 'DONE':
        return 'DONE'
    else:
        return 'INTEREST'


def handler_done(server_client_socket):
    # todo: send back the acknowledgement and close the socket
    done_response = 'DONE_OK'
    server_client_socket.send(done_response.encode('utf-8'))
    server_client_socket.close()


def handler_interest(server_peer, server_client_socket, interest_request, server_peer_lock, ):
    piece_index = get_interest_piece_index(interest_request)
    # todo: send the piece back to the peer client
    with open(server_peer.file, 'rb') as f:
        read_index = piece_index * get_piece_length(server_peer.torrent)
        f.seek(read_index)
        piece_data = f.read(get_piece_length(server_peer.torrent))
        server_client_socket.send(piece_data)
        client_ip, client_port = server_client_socket.getpeername()
        if INFO:
            handler_logger.info(f'Uploaded piece [{piece_index}] to [{client_ip}][{client_port}]')
    server_peer.update_peer_uploaded()


def handler_having(server_client_socket, peer_pieces_tracking):
    # Convert the dictionary to a JSON string
    json_data = json.dumps(peer_pieces_tracking)

    # Get the length of the JSON data
    json_length = len(json_data)

    # Pack the length of the JSON data into a 4-byte integer (big-endian)
    length_header = struct.pack('!I', json_length)

    # Send the length header followed by the JSON data (encoded in utf-8)
    server_client_socket.send(length_header)
    server_client_socket.send(json_data.encode('utf-8'))