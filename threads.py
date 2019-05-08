from __future__ import print_function, division, absolute_import

import threading
import time

import serial

from waterprogram import *# write_order, Order, write_i8, decode_order
from utilities import *# queue

rate = 1 / 2000  # 2000 Hz (limit the rate of communication with the arduino)


"""
Queues: communicate between threads
A thread that has the data puts them on the queue (a.k.a producer)
The other thread picks items from the queue (a.k.a consumer).

"""
class CommandThread(threading.Thread):
    """
    Thread that send orders to the arduino
    it blocks if there no more send_token left.

    :param serial_file: (Serial object)
    :param command_queue: (Queue)
    :param exit_event: (Threading.Event object)
    :param n_received_tokens: (threading.Semaphore)
    :param serial_lock: (threading.Lock)
    """

    def __init__(self, serial_file, command_queue, exit_event, n_received_tokens, serial_lock):
        threading.Thread.__init__(self)
        self.deamon = True
        self.serial_file = serial_file
        self.command_queue = command_queue
        self.exit_event = exit_event
        self.n_received_tokens = n_received_tokens
        self.serial_lock = serial_lock
    """
    Method representing the thread’s activity.
    You may override this method in a subclass. 
    The standard run() method invokes the callable object passed to the object’s 
    constructor as the target argument, if any, with sequential and keyword arguments 
    taken from the args and kwargs arguments, respectively.
    """
    def run(self):
        while not self.exit_event.is_set():
            self.n_received_tokens.acquire()
            if self.exit_event.is_set():
                break
            try:
                order, param = self.command_queue.get_nowait()
            except queue.Empty:
                time.sleep(rate)
                self.n_received_tokens.release()
                continue

            with self.serial_lock:

                """ 
                write_order(self.serial_file, order)
                write_i8(self.serial_file, param)
                Equivalent to write_i8(serial_file, Order.MOTOR.value)
                """

                write_order(self.serial_file, order)
                write_i8(self.serial_file, param)
            time.sleep(rate)
        print("Command Thread Exited")


class ListenerThread(threading.Thread):
    """
    Thread that listen to the Arduino
    It is used to add send_tokens to the n_received_token

    :param serial_file: (Serial object)
    :param exit_event: (threading.Event object)
    :param n_received_tokens: (threading.Semaphore)
    :param serial_lock: (threading.Lock)
    """

    def __init__(self, serial_file, exit_event, n_received_tokens, serial_lock):
        threading.Thread.__init__(self)
        self.deamon = True
        self.serial_file = serial_file
        self.exit_event = exit_event
        self.n_received_tokens = n_received_tokens
        self.serial_lock = serial_lock
        self.start_received = False
        self.messages = []
        self.checksum = 0
        self.byte_array = []

    def run(self):
        while not self.exit_event.is_set():
            try:
                start_byte = bytearray(self.serial_file.read(1))
            except serial.SerialException:
                time.sleep(rate)
                continue
            if not start_byte:
                time.sleep(rate)
                continue
            start_byte = start_byte[0]
            with self.serial_lock:
                try:
                    order = Order(start_byte)
                except ValueError:
                    continue

                if order == Order.START_BYTE:
                    self.start_received = True

                if self.start_received:
                    try:
                        byte_array = bytearray(self.serial_file.read_until(Order.CHECKSUM.value, size=None))
                    except serial.SerialException:
                        time.sleep(rate)
                        continue
                    if not byte_array:
                        time.sleep(rate)
                        continue

                    for i in byte_array:
                        byte = i
                        self.checksum = self.checksum + byte
                        self.messages.append(self, byte)
                    received_checksum = bytearray(self.serial_file.read(1))
                    received_checksum = received_checksum[0]
                    if self.checksum-received_checksum == 0:
                        decode_order(self.messages)
                    self.n_received_tokens.release()
                    self.checksum = 0
                    self.messages = []
            time.sleep(rate)
        print("Listener Thread Exited")
