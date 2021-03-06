import signal
import sys

import killerbee3
from killerbee3 import *


class ZigbeeSniffer():
    """
    Sniffing zigbee packets in a nearby zigbee network.
    A substantial portion of this class was written by contributors of the killerbee framework.
    """
    def __init__(self, file, devstring, channel=11, count=10):
        try:
            self.kb = KillerBee(device=devstring)
        except KBInterfaceError as e:
            print(("Interface Error: {0}".format(e)))
            sys.exit(-1)
        self.channel = channel
        self.file = file
        self.count = count
        self.pcap_dumper = killerbee3.PcapDumper(datalink=killerbee3.DLT_IEEE802_15_4, savefile=file)

    def interrupt(self, signum, frame, packetcount):
        self.kb.sniffer_off()
        self.kb.close()
        if self.pcap_dumper:
            self.pcap_dumper.close()
        print(("{0} packets captured".format(packetcount)))
        sys.exit(0)

    def sniff_packets(self):
        packetcount = 0
        signal.signal(signal.SIGINT, self.interrupt)
        if not self.kb.is_valid_channel(self.channel):
            print("ERROR: Must specify a valid IEEE 802.15.4 channel for the selected device.")
            self.kb.close()
            sys.exit(1)
        self.kb.set_channel(self.channel)
        self.kb.sniffer_on()
        print(("\nListening on \'{0}\', link-type DLT_IEEE802_15_4, capture size 127 bytes, channel {1}".format(
            self.kb.get_dev_info()[0], self.channel)))

        rf_freq_mhz = (self.channel - 10) * 5 + 2400
        while self.count != packetcount:
            packet = self.kb.pnext()
            # packet[1] is True if CRC is correct, check removed to have promiscous capture regardless of CRC
            if packet != None:  # and packet[1]:
                packetcount += 1
                if self.pcap_dumper:
                    self.pcap_dumper.pcap_dump(packet['bytes'], ant_dbm=packet['dbm'], freq_mhz=rf_freq_mhz)
        self.kb.sniffer_off()
        self.kb.close()
        if self.pcap_dumper:
            self.pcap_dumper.close()
        print(("{0} packets captured".format(packetcount)))



    def __getnetworkkey(self, packet):
        """
        Look for the presence of the APS Transport Key command, revealing the
        network key value.
        """
        try:
            dot154_pkt_parser = Dot154PacketParser()
            zb_nwk_pkt_parser = ZigBeeNWKPacketParser()
            zb_aps_pkt_parser = ZigBeeAPSPacketParser()

            # Process MAC layer details
            dot154_payload = dot154_pkt_parser.pktchop(packet)[-1]
            if dot154_payload == None:
                return

            # Process NWK layer details
            nwk_payload = zb_nwk_pkt_parser.pktchop(dot154_payload)[-1]
            if nwk_payload == None:
                return

            # Process the APS layer details
            aps_chop = zb_aps_pkt_parser.pktchop(nwk_payload)
            if aps_chop == None:
                return

            # See if this is an APS Command frame
            apsfc = ord(aps_chop[0])
            if (apsfc & ZBEE_APS_FCF_FRAME_TYPE) != ZBEE_APS_FCF_CMD:
                return

            # Delivery mode is Normal Delivery (0)
            apsdeliverymode = (apsfc & ZBEE_APS_FCF_DELIVERY_MODE) >> 2
            if apsdeliverymode != 0:
                return

            # Ensure Security is Disabled
            if (apsfc & ZBEE_APS_FCF_SECURITY) == 1:
                return

            aps_payload = aps_chop[-1]

            # Check payload length, must be at least 35 bytes
            # APS cmd | key type | key | sequence number | dest addr | src addr
            if len(aps_payload) < 35:
                return

            # Check for APS command identifier Transport Key (0x05)
            if ord(aps_payload[0]) != 5:
                return

            # Transport Key Frame, get the key type.  Network Key is 0x01, no
            # other keys should be sent in plaintext
            if ord(aps_payload[1]) != 1:
                print("Possible key or false positive?")
                return

            # Reverse these fields
            networkkey = aps_payload[2:18][::-1]
            destaddr = aps_payload[19:27][::-1]
            srcaddr = aps_payload[27:35][::-1]
            for x in networkkey[0:15]:
                print("NETWORK KEY FOUND: ",
                sys.stdout.write("%02x:" % ord(x)))
            print ("%02x" % ord(networkkey[15]))
            for x in aps_payload[2:17]:
                print("      (Wireshark): ",
                sys.stdout.write("%02x:" % ord(x)))
            print("%02x" % ord(aps_payload[17]))
            for x in destaddr[0:7]:
                print("  Destination MAC Address: ",
                sys.stdout.write("%02x:" % ord(x)))
            print ("%02x" % ord(destaddr[7]))
            for x in srcaddr[0:7]:
                print("  Source MAC Address:      ",
                sys.stdout.write("%02x:" % ord(x)))
            print("%02x" % ord(srcaddr[7]))

        except Exception as e:
            # print e
            return

    def sniff_key(self):
        print ("\nProcessing %s" % self.file)
        if not os.path.exists(self.file):
            print("ERROR: Input file \"%s\" does not exist." % self.file)
            # Check if the input file is libpcap; if not, assume SNA.
        cap = None
        pcap_reader = None
        try:
            pcap_reader = PcapReader(self.file)
        except Exception as e:
            if e.args == ('Unsupported pcap header format or version',):
                # Input file was not pcap, open it as SNA
                cap = DainTreeReader(self.file)

        # Following exception
        if cap is None:
            cap = pcap_reader
        while 1:
            packet = cap.pnext()
            if packet[1] is None:
                # End of capture
                break
            # Add additional key/password/interesting-stuff here
            self.__getnetworkkey(packet[1])
        cap.close()
        print("Processed captured file.")

    def __del__(self):
        self.kb.close()