"""
Time-Locked Gift Contract (Vesting)
1. Giver locks funds with a specific Deadline and Beneficiary.
2. Taker claims funds after the deadline passes.
"""

import os
import time
from dataclasses import dataclass
from typing import List

import cbor2
from blockfrost import ApiUrls
from pycardano import *

# --- 1. Configuration & Setup ---

NETWORK = Network.TESTNET  # or Network.TESTNET depending on your setup


def get_env_val(key):
    val = os.environ.get(key)
    if not val:
        raise Exception(f"Environment variable {key} is not set!")
    return val


# Load your Wallet (The "Giver" and "Taker" are the same person in this test)
payment_skey = PaymentSigningKey.load(get_env_val("PAYMENT_KEY_PATH"))
payment_vkey = PaymentVerificationKey.from_signing_key(payment_skey)
my_address = Address(payment_vkey.hash(), network=NETWORK)

chain_context = BlockFrostChainContext(
    project_id=get_env_val("BLOCKFROST_ID"),
    base_url=ApiUrls.preprod.value,
)


# --- 2. Define Custom Datum (The "Interesting" Part) ---

@dataclass
class VestingDatum(PlutusData):
    """
    We define a class that matches the struct in our Plutus on-chain code.
    It holds 2 fields:
    1. beneficiary: The PubKeyHash of the person who can claim.
    2. deadline: The POSIX time (in milliseconds) after which they can claim.
    """
    CONSTR_ID = 0  # Matches the constructor index in Plutus
    beneficiary: bytes
    deadline: int


# --- 3. Load the Script ---

# Assuming you have a compiled 'vesting.plutus' file
# (If you don't, this part will fail, but the structure remains valid)
try:
    with open("vesting.plutus", "r") as f:
        script_hex = f.read().strip()
        vesting_script = PlutusV2Script(cbor2.loads(bytes.fromhex(script_hex)))
        script_hash = plutus_script_hash(vesting_script)
        script_address = Address(script_hash, network=NETWORK)
except FileNotFoundError:
    print("⚠️ 'vesting.plutus' not found. Please compile your Aiken/Plutus script first.")
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
    print("Transaction check timed out (it might still confirm later).")


def submit_tx(tx):
    print("Submitting transaction...")
    chain_context.submit_tx(tx)
    wait_for_tx(str(tx.id))


# --- 5. Phase 1: Locking the Funds (The Gift) ---

def lock_funds(amount_lovelace, lock_duration_seconds):
    print("\n--- LOCKING FUNDS ---")

    # Calculate deadline (Current time + duration) in milliseconds
    current_time_ms = int(time.time() * 1000)
    deadline_ms = current_time_ms + (lock_duration_seconds * 1000)

    print(f"Locking {amount_lovelace / 1000000} ADA until timestamp: {deadline_ms}")

    # Create our Custom Datum
    # We use our own wallet hash as the beneficiary
    datum = VestingDatum(
        beneficiary=bytes(payment_vkey.hash()),
        deadline=deadline_ms
    )

    builder = TransactionBuilder(chain_context)
    builder.add_input_address(my_address)

    # Add output to script address with our custom Datum
    builder.add_output(
        TransactionOutput(script_address, amount_lovelace, datum=datum)
    )

    signed_tx = builder.build_and_sign([payment_skey], change_address=my_address)
    submit_tx(signed_tx)
    return deadline_ms


# --- 6. Phase 2: Claiming the Funds (The Withdraw) ---

def claim_funds(deadline_ms):
    print("\n--- CLAIMING FUNDS ---")

    # Find the UTXO at the script address
    script_utxo = None

    # We scan script UTXOs to find one that belongs to us (checking the datum)
    for utxo in chain_context.utxos(script_address):
        if not utxo.output.datum:
            continue

        try:
            # We attempt to interpret the datum as our VestingDatum class
            # This is how we "read" the on-chain data back into Python
            datum_obj = VestingDatum.from_cbor(utxo.output.datum.cbor)

            if datum_obj.beneficiary == bytes(payment_vkey.hash()):
                print(f"Found our gift! Amount: {utxo.output.amount.coin}")
                script_utxo = utxo
                break
        except Exception as e:
            # If the datum doesn't match our class structure, ignore it
            continue

    if not script_utxo:
        print("No suitable UTXO found to claim.")
        return

    # Create the Redeemer (Unit/Void because the logic is in the context, not the action)
    # This corresponds to '()', or 'Void' in many Plutus scripts
    redeemer = Redeemer(PlutusData())

    builder = TransactionBuilder(chain_context)

    # Add the script input
    # Note: For efficiency, we usually use reference scripts (like your previous example),
    # but here we attach the script directly for simplicity.
    builder.add_script_input(script_utxo, vesting_script, datum=None, redeemer=redeemer)

    # CRITICAL: Validity Interval
    # We must tell the chain "This transaction is valid FROM this time forward".
    # This proves to the script that the current time > deadline.

    # Convert ms back to slots (approximate for simplicity, or use chain_context for exact slot)
    # PyCardano normally handles slot conversion if we set validity_start

    # We set validity start to the deadline + 1 second to be safe
    # In a real app, you would verify the current slot from the chain.
    current_slot = chain_context.last_block_slot

    # We add a "validity start" constraint.
    # The transaction will fail if the current chain slot is earlier than this.
    builder.validity_start = current_slot

    # Add our required signature (because the script checks if 'beneficiary' signed it)
    builder.required_signers = [payment_vkey.hash()]

    # Send the funds back to us
    builder.add_output(TransactionOutput(my_address, script_utxo.output.amount.coin))

    print("Building transaction with time constraints...")
    # We have to handle collateral for smart contract interactions
    builder.collaterals = [chain_context.utxos(my_address)[0]]

    signed_tx = builder.build_and_sign([payment_skey], change_address=my_address)
    submit_tx(signed_tx)


# --- Execution Flow ---

if __name__ == "__main__":
    # 1. Lock 10 ADA for 60 seconds
    deadline = lock_funds(10000000, 60)

    print("\nWaiting for lock to expire (60s)...")
    time.sleep(65)  # Wait a bit extra to ensure block time passes

    # 2. Claim the ADA
    claim_funds(deadline)