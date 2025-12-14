import rsa
import base64

def load_public_key(filepath='public.pem'):
    with open(filepath, 'rb') as f:
        return rsa.PublicKey.load_pkcs1(f.read())

def verify_signature(sender, data, signature_b64, pubkey_path='public.pem'):
    try:
        public_key = load_public_key(pubkey_path)
        signature = base64.b64decode(signature_b64)
        rsa.verify(data.encode(), signature, public_key)
        return True
    except Exception as e:
        print(f"[!] Signature verification failed: {e}")
        return False