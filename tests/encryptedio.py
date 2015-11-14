import hashlib
import unittest
import tempfile
import storjnode


class TestEncryptedIO(unittest.TestCase):

    def test_roundtrip(self):
        input_path = __file__
        encrypted_path = tempfile.mktemp()
        output_path = tempfile.mktemp()

        # encrypt
        with open(input_path, 'rb') as fi, open(encrypted_path, 'wb') as fo:
            storjnode.encryptedio.symmetric_encrypt(fi, fo, b"test")

        # decrypt
        with open(encrypted_path, 'rb') as fi, open(output_path, 'wb') as fo:
            storjnode.encryptedio.symmetric_decrypt(fi, fo, b"test")

        # check hashes
        with open(input_path, 'rb') as input_file:
            input_hash = hashlib.sha256(input_file.read()).hexdigest()
        with open(output_path, 'rb') as output_file:
            output_hash = hashlib.sha256(output_file.read()).hexdigest()
        self.assertEqual(input_hash, output_hash)

        # TODO add openssl compatibility tests (already tested manually)


if __name__ == '__main__':
    unittest.main()
