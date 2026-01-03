"""

Off-chain code of taker and giver in fortytwo.

"""


"""
Step1 Store Script
tx = b45b7df1c44e27915e8d192906d4f4672dee15fb0b6dc0d5ffae9b6c49988df7
input:
    giver_address, payment_address = addr_test1vqd37qs9y86z2v4gmjr78nuq2snactwvwwk8yuaz53fz37s5nh4fx
output:
    Change UTxO  = addr_test1vqd37qs9y86z2v4gmjr78nuq2snactwvwwk8yuaz53fz37s5nh4fx (Consumed by transaction)
    Inline script UTxO = addr_test1vqd37qs9y86z2v4gmjr78nuq2snactwvwwk8yuaz53fz37s5nh4fx (script hash = 1534828b3f28a816a421137fba569f855c2ffa3876649638e78a096c)

Step2 Lock Funds
tx = 644dd703f28bd9368a59864aa91bcf81777054af1e4456b4ac39789e45df9948
input:
    giver_address = addr_test1vqd37qs9y86z2v4gmjr78nuq2snactwvwwk8yuaz53fz37s5nh4fx
output:
    giver_address = addr_test1vqd37qs9y86z2v4gmjr78nuq2snactwvwwk8yuaz53fz37s5nh4fx
    script_address = addr_test1wq2nfq5t8u52s94yyyfhlwjkn7z4ctl68pmxf93cu79qjmq2hd8h8  (inline datum =  9e1199a988ba72ffd6e9c269cadb3b53b5f360ff99f112d9b2ee30c4d74ad88b)
    
Step3 Unlock Funds
tx = cbcae101bc064f7f24d1b43e9644d6250fcfbb990965c11dff5a84ce79a2c484
input:
    script_address = addr_test1wq2nfq5t8u52s94yyyfhlwjkn7z4ctl68pmxf93cu79qjmq2hd8h8 (inline datum =  9e1199a988ba72ffd6e9c269cadb3b53b5f360ff99f112d9b2ee30c4d74ad88b)
output:
    giver_address = addr_test1vqd37qs9y86z2v4gmjr78nuq2snactwvwwk8yuaz53fz37s5nh4fx
    giver_address = addr_test1vqd37qs9y86z2v4gmjr78nuq2snactwvwwk8yuaz53fz37s5nh4fx

"""




import os

import cbor2
from blockfrost import ApiUrls
from retry import retry

from pycardano import *

NETWORK = Network.TESTNET


def get_env_val(key):
    val = os.environ.get(key)
    if not val:
        raise Exception(f"Environment variable {key} is not set!")
    return val


payment_skey = PaymentSigningKey.load(get_env_val("PAYMENT_KEY_PATH"))
payment_vkey = PaymentVerificationKey.from_signing_key(payment_skey)

chain_context = BlockFrostChainContext(
    project_id=get_env_val("BLOCKFROST_ID"),
    base_url=ApiUrls.preprod.value,
)


@retry(delay=20)
def wait_for_tx(tx_id):
    chain_context.api.transaction(tx_id)
    print(f"Transaction {tx_id} has been successfully included in the blockchain.")


def submit_tx(tx):
    print("############### Transaction created ###############")
    print(tx)
    print(tx.to_cbor_hex())
    print("############### Submitting transaction ###############")
    chain_context.submit_tx(tx)
    wait_for_tx(str(tx.id))


with open("fortytwoV2.plutus", "r") as f:
    script_hex = f.read()
    forty_two_script = PlutusV2Script(cbor2.loads(bytes.fromhex(script_hex)))


script_hash = plutus_script_hash(forty_two_script)

script_address = Address(script_hash, network=NETWORK)

giver_address = Address(payment_vkey.hash(), network=NETWORK)

builder = TransactionBuilder(chain_context)
builder.add_input_address(giver_address)
builder.add_output(TransactionOutput(giver_address, 50000000, script=forty_two_script))

signed_tx = builder.build_and_sign([payment_skey], giver_address)

print("############### Transaction created ###############")
print(signed_tx)
print("############### Submitting transaction ###############")
submit_tx(signed_tx)


# ----------- Send ADA to the script address ---------------

builder = TransactionBuilder(chain_context)
builder.add_input_address(giver_address)
datum = 42
builder.add_output(TransactionOutput(script_address, 50000000, datum=datum))

signed_tx = builder.build_and_sign([payment_skey], giver_address)

print("############### Transaction created ###############")
print(signed_tx)
print("############### Submitting transaction ###############")
submit_tx(signed_tx)

# ----------- Taker take ---------------

redeemer = Redeemer(42)

utxo_to_spend = None

# Spend the utxo with datum 42 sitting at the script address
for utxo in chain_context.utxos(script_address):
    print(utxo)
    if utxo.output.datum:
        utxo_to_spend = utxo
        break

# Find the reference script utxo
reference_script_utxo = None
for utxo in chain_context.utxos(giver_address):
    if utxo.output.script and utxo.output.script == forty_two_script:
        reference_script_utxo = utxo
        break

taker_address = Address(payment_vkey.hash(), network=NETWORK)

builder = TransactionBuilder(chain_context)

builder.add_script_input(utxo_to_spend, script=reference_script_utxo, redeemer=redeemer)
take_output = TransactionOutput(taker_address, 25123456)
builder.add_output(take_output)

signed_tx = builder.build_and_sign([payment_skey], taker_address)

print("############### Transaction created ###############")
print(signed_tx)
print("############### Submitting transaction ###############")
submit_tx(signed_tx)
