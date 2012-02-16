import hashlib
import StringIO
import bencode
import os
import logging


class HashCheck:

    def __init__(self, torrent_path):
        if not os.path.isfile(torrent_path):
            raise Exception('Unable to open torrent file : %s' % torrent_path)

        torrent = open(torrent_path, 'rb')
        self.meta = bencode.bdecode(torrent.read())
        self.info = self.meta['info']
        self.piece_length = self.info['piece length']
        self.pieces = self.info['pieces']
        self.pieces_io = StringIO.StringIO(self.pieces)

        self.piece_count = len(self.pieces) / 20
        self.file_list = self._get_files()
        self.file_count = len(self.file_list)

    def check(self, path):
        '''
        for x in self.get_pieces():
            logging.info('%s' % x.encode("hex"))
        '''
        return

    def get_pieces(self):
        pieces = StringIO.StringIO(self.pieces)
        while 1:
            piece_data = pieces.read(20)
            if piece_data == "":
                break

            yield piece_data

    def _get_files(self):
        output = []
        name = self.info['name']
        offset = 0
        if 'files' in self.info:
            for f in self.info['files']:
                file_path = os.sep.join([name] + f['path'])
                output.append({'path': file_path, 'length': f['length'], 'offset': offset})
                offset += f['length']
        else:
            output.append({'path': name, 'length': self.info['length'], 'offset': offset})
        return output

    def check_chunks(self, chunk, number):
        output = []
        for x in xrange(chunk, chunk + number):
            if x >= self.piece_count:
                break

            output.append(self.check_chunk(x))
        return output

    def check_chunk(self, chunk):
        if chunk >= self.piece_count:
            message = 'trying to check non existant chunk [chunk:%d] [total_chunks:%d]' % (chunk, self.piece_count)
            logging.error(message)
            return {'status': 'fail', 'reason': message, 'chunk': chunk}

        file_list = self.get_chunk_files(chunk)
        hash_data = []

        sha1 = hashlib.sha1()
        for f in file_list:
            start_byte = f['start']
            end_byte = f['end']
            byte_count = end_byte - start_byte

            file_path = f['file']['path']

            logging.info('[chunk:%d] reading %d bytes starting @ %d from %s' %
                        (chunk, byte_count, start_byte, file_path))

            if not os.path.isfile(file_path):
                base_name = os.path.basename(file_path)
                if os.path.isfile(base_name):
                    file_path = base_name
                else:
                    return {'status': 'fail', 'reason': 'Unable to find file "%s"' % file_path, 'chunk': chunk}

            data_file = open(file_path, 'rb')
            if start_byte > 0:
                data_file.seek(start_byte)

            bytes = data_file.read(byte_count)
            data_file.close()

            if len(bytes) != (byte_count):
                message = '[chunk:%d] error reading from file : %s requested %d bytes only got %d' % (chunk, file_path, byte_count, len(hash_data))
                logging.error(message)
                return {'status': 'fail', 'reason': message, 'chunk': chunk}

            sha1.update(bytes)

        sha1sum = sha1.digest()
        chunkhash = self.get_piece(chunk)

        if sha1sum == chunkhash:
            return {'status': 'ok', 'chunk': chunk, 'hash': sha1sum.encode('hex')}

        message = '[chunk:%d] [file:%s] error hash does not match %s vs %s' % (chunk, file_path,  sha1sum.encode('hex'), chunkhash.encode('hex'))
        return {'status': 'fail', 'reason': message, 'chunk': chunk}

    def get_piece(self, chunk):
        chunk_start = chunk * 20
        return self.pieces[chunk_start:chunk_start + 20]

    def get_chunk_files(self, chunk):
        offset = chunk * self.piece_length

        file_index = -1
        for i in xrange(self.file_count):
            cur_file = self.file_list[i]
            if offset < cur_file['offset'] + cur_file['length']:
                file_index = i
                break

        if file_index == -1:
            raise Exception('error finding chunk data for [chunk:%d] [offset:%d] [count:%d]' % (chunk, offset, self.file_count))

        start_file = self.file_list[file_index]
        start_offset = offset - start_file['offset']
        end_offset = start_offset + self.piece_length
        remaning = 0
        if end_offset > start_file['length']:
            remaning = end_offset - start_file['length']
            logging.info('piece splits file %d - %d = %d' % (end_offset, start_file['length'], remaning))
            end_offset = start_file['length']

        output = [{'file': start_file, 'start': start_offset, 'end': end_offset}]

        while remaning > 0:
            file_index += 1
            if file_index >= self.file_count:
                break

            obj = {'file': self.file_list[file_index], 'start': 0}
            file_length = obj['file']['length']
            if remaning > file_length:
                remaning -= file_length
                obj['end'] = file_length
            else:
                obj['end'] = remaning
                remaning = 0
            output.append(obj)

        return output
