import sys
import hashlib
import json
import os
from time import time
from uuid import uuid4
from flask import Flask, request, jsonify, render_template_string
import requests
from urllib.parse import urlparse
from utils_crypto import verify_signature

CHAIN_FILE = "chain_data.json"

class Blockchain:
    def __init__(self):
        self.nodes = set()
        self.chain = []
        self.current_transactions = []
        self.difficulty_target = "0000"
        if os.path.exists(CHAIN_FILE):
            self.load_chain()
        else:
            genesis_hash = self.hash_block("genesis_block")
            self.append_block(
                nonce=self.proof_of_work(0, genesis_hash, []),
                hash_of_previous_block=genesis_hash
            )
            self.save_chain()

    def save_chain(self):
        with open(CHAIN_FILE, "w") as f:
            json.dump(self.chain, f, indent=4)

    def load_chain(self):
        with open(CHAIN_FILE, "r") as f:
            self.chain = json.load(f)

    def add_node(self, address):
        if not address.startswith("http://") and not address.startswith("https://"):
            address = f"http://{address}"
        parsed_url = urlparse(address)
        if parsed_url.netloc:
            self.nodes.add(parsed_url.netloc)

    def valid_chain(self, chain):
        if not chain or not isinstance(chain, list):
            return False
        try:
            last_block = chain[0]
            current_index = 1
            while current_index < len(chain):
                block = chain[current_index]
                if block['hash_of_previous_block'] != self.hash_block(last_block):
                    return False
                if not self.valid_proof(
                    current_index,
                    block['hash_of_previous_block'],
                    block['transactions'],
                    block['nonce']
                ):
                    return False
                last_block = block
                current_index += 1
            return True
        except Exception as e:
            print(f"[!] Error in valid_chain: {e}")
            return False

    def update_blockchain(self):
        neighbours = self.nodes
        new_chain = None
        max_length = len(self.chain)

        for node in neighbours:
            try:
                response = requests.get(f'http://{node}/blockchain')
                if response.status_code == 200:
                    length = response.json()['length']
                    chain = response.json()['chain']
                    if length > max_length and self.valid_chain(chain):
                        max_length = length
                        new_chain = chain
            except Exception as e:
                print(f"[!] Gagal sync ke node {node}: {e}")

        if new_chain:
            self.chain = new_chain
            self.save_chain()
            return True
        return False

    def hash_block(self, block):
        block_encoded = json.dumps(block, sort_keys=True).encode()
        return hashlib.sha256(block_encoded).hexdigest()

    def proof_of_work(self, index, hash_of_previous_block, transactions):
        nonce = 0
        while not self.valid_proof(index, hash_of_previous_block, transactions, nonce):
            nonce += 1
        return nonce

    def valid_proof(self, index, hash_of_previous_block, transactions, nonce):
        content = f'{index}{hash_of_previous_block}{transactions}{nonce}'.encode()
        content_hash = hashlib.sha256(content).hexdigest()
        return content_hash[:len(self.difficulty_target)] == self.difficulty_target

    def append_block(self, nonce, hash_of_previous_block):
        block = {
            'index': len(self.chain),
            'timestamp': time(),
            'transactions': self.current_transactions,
            'nonce': nonce,
            'hash_of_previous_block': hash_of_previous_block
        }
        self.current_transactions = []
        self.chain.append(block)
        self.save_chain()
        return block

    def get_balance_of(self, address):
        balance = 0
        for block in self.chain:
            for tx in block['transactions']:
                if tx['recipient'] == address:
                    balance += tx['amount']
                elif tx['sender'] == address:
                    balance -= tx['amount']
        return balance

    def add_transaction(self, sender, recipient, amount, signature=None):
        if sender != "0":
            message = f"{sender}:{recipient}:{amount}"
            if not signature or not verify_signature(sender, message, signature):
                raise ValueError("Signature tidak valid atau hilang")

            if self.get_balance_of(sender) < amount:
                raise ValueError(f"Saldo {sender} tidak cukup.")

        self.current_transactions.append({
            'sender': sender,
            'recipient': recipient,
            'amount': amount,
            'currency': "DNR"
        })
        return self.last_block['index'] + 1

    @property
    def last_block(self):
        return self.chain[-1]

# Flask App
app = Flask(__name__)
node_identifier = str(uuid4()).replace('-', "")
blockchain = Blockchain()

@app.route('/')
def home():
    return "<h2 style='text-align:center'>🧱 DSS_Chain 2.0 Aktif</h2><p>Lihat <a href='/explorer'>/explorer</a></p>"

@app.route('/transactions/new', methods=['POST'])
def new_transaction():
    values = request.get_json()
    required = ['sender', 'recipient', 'amount', 'signature']
    if not all(k in values for k in required):
        return jsonify({'error': 'Field kurang'}), 400
    try:
        index = blockchain.add_transaction(
            values['sender'], values['recipient'], values['amount'], values['signature']
        )
        return jsonify({'message': f'Transaksi akan masuk ke block {index}'}), 201
    except ValueError as e:
        return jsonify({'error': str(e)}), 400

@app.route('/mine', methods=['GET'])
def mine_block():
    blockchain.add_transaction("0", node_identifier, 1)
    last_hash = blockchain.hash_block(blockchain.last_block)
    nonce = blockchain.proof_of_work(len(blockchain.chain), last_hash, blockchain.current_transactions)
    block = blockchain.append_block(nonce, last_hash)
    return jsonify({
        'message': 'Block ditambahkan!',
        'block': block
    })

@app.route('/blockchain', methods=['GET'])
def full_chain():
    return jsonify({
        'chain': blockchain.chain,
        'length': len(blockchain.chain)
    })

@app.route('/nodes/add_nodes', methods=['POST'])
def add_nodes():
    values = request.get_json()
    nodes = values.get('nodes')
    if not nodes:
        return "Missing nodes", 400
    for node in nodes:
        blockchain.add_node(node)
    return jsonify({'message': 'Node ditambahkan', 'nodes': list(blockchain.nodes)})

@app.route('/nodes/sync', methods=['GET'])
def sync_nodes():
    updated = blockchain.update_blockchain()
    msg = 'Blockchain diperbarui' if updated else 'Blockchain sudah up-to-date'
    return jsonify({'message': msg, 'chain': blockchain.chain})

@app.route('/nodes', methods=['GET'])
def list_nodes():
    return jsonify({'nodes': list(blockchain.nodes)})

@app.route('/balance/<address>', methods=['GET'])
def check_balance(address):
    balance = blockchain.get_balance_of(address)
    return jsonify({'address': address, 'balance': balance, 'currency': 'DNR'})

@app.route('/supply', methods=['GET'])
def supply():
    total = 0
    for block in blockchain.chain:
        for tx in block['transactions']:
            if tx['currency'] == "DNR":
                total += tx['amount']
    return jsonify({'total_supply': total, 'currency': 'DNR'})

@app.route('/explorer', methods=['GET'])
def explorer():
    html = """
    <h1 style="text-align:center">🧱 DSS_Chain Explorer</h1>
    {% for block in chain %}
    <div style="border:1px solid #ccc; padding:10px; margin:10px">
        <strong>Block #{{ block.index }}</strong><br/>
        Hash Sebelumnya: {{ block.hash_of_previous_block }}<br/>
        Nonce: {{ block.nonce }}<br/>
        <em>Transaksi:</em>
        <ul>
        {% for tx in block.transactions %}
            <li>{{ tx.sender }} ➜ {{ tx.recipient }}: {{ tx.amount }} {{ tx.currency }}</li>
        {% endfor %}
        </ul>
    </div>
    {% endfor %}
    """
    return render_template_string(html, chain=blockchain.chain)

if __name__ == '__main__':
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 5000
    app.run(host='0.0.0.0', port=port)