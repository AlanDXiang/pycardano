"""
Time-Locked Gift Contract (Vesting)
"""

import os
import time
from dataclasses import dataclass

import cbor2
from blockfrost import ApiUrls
from pycardano import *

# --- 1. Configuration & Setup ---

NETWORK = Network.TESTNET

def get_env_val(key):
    val = os.environ.get(key)
    if not val:
        raise Exception(f"Environment variable {key} is not set!")
    return val

# Load your Wallet
payment_skey = PaymentSigningKey.load(get_env_val("PAYMENT_KEY_PATH"))
payment_vkey = PaymentVerificationKey.from_signing_key(payment_skey)
my_address = Address(payment_vkey.hash(), network=NETWORK)

chain_context = BlockFrostChainContext(
    project_id=get_env_val("BLOCKFROST_ID"),
    base_url=ApiUrls.preprod.value,
)

# --- 2. Define Custom Datum ---

@dataclass
class VestingDatum(PlutusData):
    CONSTR_ID = 0
    beneficiary: bytes
    deadline: int

# --- 3. Load the Script ---

try:
    with open("vesting.plutus", "r") as f:
        script_hex = f.read().strip()
        vesting_script = PlutusV2Script(cbor2.loads(bytes.fromhex(script_hex)))
        script_hash = plutus_script_hash(vesting_script)
        script_address = Address(script_hash, network=NETWORK)
except FileNotFoundError:
    print("⚠️ 'vesting.plutus' not found.")
    exit()

# --- 4. Helper Functions ---

def wait_for_tx(tx_id):
    print(f"Waiting for {tx_id}...")
    for i in range(20):
        try:
            chain_context.api.transaction(tx_id)
            print("Confirmed!")
            return
        except:
            time.sleep(5)
    print("Transaction check timed out.")

def submit_tx(tx):
    print("Submitting transaction...")
    chain_context.submit_tx(tx)
    wait_for_tx(str(tx.id))

# --- 5. Phase 1: Locking the Funds ---

def lock_funds(amount_lovelace, lock_duration_seconds):
    print("\n--- LOCKING FUNDS ---")

    current_time_ms = int(time.time() * 1000)
    deadline_ms = current_time_ms + (lock_duration_seconds * 1000)

    print(f"Locking {amount_lovelace / 1000000} ADA until timestamp: {deadline_ms}")

    # ### CRITICAL FIX HERE ###
    # Use .payload to get the raw 28 bytes.
    # bytes(obj) would return the CBOR encoded bytes (30 bytes), which fails verification.
    beneficiary_bytes = payment_vkey.hash().payload

    datum = VestingDatum(
        beneficiary=beneficiary_bytes,
        deadline=deadline_ms
    )

    builder = TransactionBuilder(chain_context)
    builder.add_input_address(my_address)
    builder.add_output(
        TransactionOutput(script_address, amount_lovelace, datum=datum)
    )

    signed_tx = builder.build_and_sign([payment_skey], change_address=my_address)
    submit_tx(signed_tx)
    return deadline_ms

# --- 6. Phase 2: Claiming the Funds ---

def claim_funds(deadline_ms):
    print("\n--- CLAIMING FUNDS ---")

    # 1. Wait for Chain Time
    while True:
        try:
            latest_block = chain_context.api.block_latest()
            chain_time_ms = latest_block.time * 1000
            print(f"Chain Time: {chain_time_ms} | Deadline: {deadline_ms}")

            if chain_time_ms > deadline_ms:
                print("Deadline passed. Proceeding.")
                break
            time.sleep(10)
        except Exception as e:
            time.sleep(5)

    # 2. Find UTXO
    script_utxo = None
    for utxo in chain_context.utxos(script_address):
        if not utxo.output.datum:
            continue
        try:
            datum_obj = VestingDatum.from_cbor(utxo.output.datum.cbor)

            # Use payload for comparison here too
            my_hash = payment_vkey.hash().payload

            if datum_obj.beneficiary == my_hash:
                print(f"Found our gift! Amount: {utxo.output.amount.coin}")
                script_utxo = utxo
                break
        except Exception:
            continue

    if not script_utxo:
        print("No suitable UTXO found to claim.")
        return

    redeemer = Redeemer(PlutusData())

    builder = TransactionBuilder(chain_context)
    builder.add_input_address(my_address)

    # Inline Datum -> datum=None
    builder.add_script_input(
        script_utxo,
        vesting_script,
        datum=None,
        redeemer=redeemer
    )

    # 3. Validity Interval & Signers
    current_slot = chain_context.last_block_slot
    builder.validity_start = current_slot
    builder.ttl = current_slot + 500

    builder.required_signers = [payment_vkey.hash()]

    builder.add_output(TransactionOutput(my_address, script_utxo.output.amount.coin))
    builder.collaterals = [chain_context.utxos(my_address)[0]]

    print("Building transaction...")
    signed_tx = builder.build_and_sign([payment_skey], change_address=my_address)
    submit_tx(signed_tx)

# --- Execution Flow ---

if __name__ == "__main__":
    deadline = lock_funds(10000000, 60)

    print("\nWaiting for lock to expire...")
    time.sleep(65)

    claim_funds(deadline)