# AP2 Payment Processor

This repository implements the first working reference **AP2 Payment Processor**.  
It demonstrates how to construct, validate, and persist **AP2 Mandates** as Verifiable Credentials (VCs), following the [AP2 0.1-alpha specification](https://ap2-protocol.org/).

---

## 📖 What is AP2?

**AP2 (Agent Protocol 2)** is an experimental open protocol for **auditable, intent-driven payments**.  
It defines a set of **Mandates** (VC types) that capture the lifecycle of a payment:

- **IntentMandate** – a user's raw intent to pay
- **CartMandate** – merchant checkout confirmation
- **PaymentMandate** – finalized payment details
- **RefundMandate** – refund of a prior payment
- **FraudFlag** – fraud evidence attached to a prior mandate

## Custom Mandate
- **NettingMandate** – settlement netting between counterparties (traditional banking sector) for EOD batch processing

Each mandate is a **W3C Verifiable Credential**, signed by the appropriate actor (user wallet, merchant, processor).  
The chain of mandates forms a **transparent, append-only audit trail**. This does NOT apply to the NettingMandate, which is a custom Mandate not known by W3C.

---

## ⚙️ What this Processor Does

This implementation provides:

- A **MandateFactory** that builds spec-compliant VCs for each mandate type.
- A **PaymentProcessor** that orchestrates flows:
  - Payment (Intent → Cart → Payment)
  - Refunds (linked to a prior PaymentMandate)
  - Fraud flags (linked to any prior mandate)
  - Netting obligations
- A **Ledger** that persists transactions and enforces invariants.
- An **AgentPrompt** loop that parses natural language commands into structured flows.

The design emphasizes:
- **Spec compliance** (contexts, schemas, RevocationList2020)
- **Auditability** (every mandate has a UUID, linkage to prior mandates, and explicit notes)
- **Extensibility** (easy to add new mandate types)

---

## 🚀 Usage

### 1. Start the Agent

1. Double click the .exe file and you will be greeted by a 'AP2>' prompt.

### Example Prompts

#### Basic Payment Flow

```
Send 5 GBP to Starbucks for Batch Brew
```
or
```
Pay 5 GBP to Starbucks for Batch Brew
```

**Produces:** IntentMandate → CartMandate → PaymentMandate

---

#### Intent-Only

```
Intent for 5 GBP to RunFree for Red Shoes in Size 44
```

**Produces:** IntentMandate

---

#### Using Raw Intent JSON

```
use ../intent_mandate_0_1.json
```

Will produce the following questions:

```
Amount for this intent: 500
Currency (default EUR): GBP
Receiver (merchant id): Footlocker
```

After this, the raw intent will be fed into the payment processor and a VC IntentMandate will be created and the full happy path will continue. The raw intent is taken directly from the AP2 Protocol website, proving spec-compliance message processing.

**Output:**

```
TXN txn-cf061aeb-01ba-4ceb-8943-66d36e74a28c | issuer:user-wallet -> Footlocker 500.0 GBP
vc_id of this PaymentMandate is: vc_id=urn:uuid:71badfed-69f9-4de4-a6aa-7dfde3865178
```

---

#### Refund Flow

```
refund urn:uuid:71badfed-69f9-4de4-a6aa-7dfde3865178 for 500 GBP
```

**Produces:**

```
[Agent] Please provide a reason for this refund: Accidental Transaction
```

The `urn:uuid:71badfed-69f9-4de4-a6aa-7dfde3865178` is the `vc_id` of the PaymentMandate, which is per-spec.

**Output:**

```
TXN refund-5ed1b74b-1d15-4476-8a4f-c55e1fddef8e | issuer:processor -> Footlocker -500.0 GBP
```

---

#### Netting Flow (Corporate Banking)

```
Send 500000 KRW from SHN to CNY settlement run DTP2 for Shares
```

**Produces:**

```
[Agent] Netting Finished.
```

This prompt triggers the new Netting path for investment banks, commercial banking and corporate banking environments. The 'PaymentMandate' will only be sent 'after' Netting has finished (EOD Batch processing simulation).

This allows AP2 to be used within the traditional confines of the corporate banking structure.

##### Example NettingMandate:

```json
{
  "@context": [
    "https://www.w3.org/2018/credentials/v1",
    "https://ap2-protocol.org/contexts/mandates/v1",
    "https://w3id.org/security/v2"
  ],
  "id": "urn:uuid:a3f79c45-9176-4427-9ade-cba800312b58",
  "type": [
    "VerifiableCredential",
    "NettingMandate"
  ],
  "issuer": "issuer:netting",
  "issuanceDate": "2025-10-05T20:57:43Z",
  "expirationDate": "2025-10-05T21:57:43Z",
  "credentialSchema": {
    "id": "https://ap2-protocol.org/schemas/mandate-schema.json",
    "type": "JsonSchemaValidator2018"
  },
  "credentialStatus": {
    "id": "https://ap2-protocol.org/status/registry#revocation-list-1",
    "type": "RevocationList2020Status"
  },
  "credentialSubject": {
    "label": "Netting obligation for settlement run DTP2",
    "note": "Netting 500000.0",
    "mandate_id": "c5c9fc56-0546-4e89-8b04-a0e600474908",
    "prev_mandate_id": "urn:uuid:2c467e21-9688-4dea-a862-408709763ccd",
    "prev_mandate_ids": [
      "urn:uuid:2c467e21-9688-4dea-a862-408709763ccd"
    ],
    "timestamp": "2025-10-05T20:57:43Z",
    "merchant_id": "CNY",
    "payment_details": {
      "amount": 500000.0,
      "currency": "KRW",
      "counterparty": "CNY",
      "settlement_run": "DTP2"
    }
  },
  "proof": {
    "type": "Ed25519Signature2020",
    "created": "2025-10-05T20:57:43Z",
    "verificationMethod": "issuer:netting#keys-1",
    "proofPurpose": "assertionMethod",
    "proofValue": "1VtvDTkTvckVFFJ5btRz56isSKDku1FNwgbWamr2wnDJwosaprrYni6ALiTimkVpXoMdB6CF8VtviDgjuY3Fy2z"
  }
}
```

##### Complete Mandate Chain Output:

```
TXN txn-f6443613-0ba8-4c31-9438-3195500d0f53 | SHN -> CNY 500000.0 KRW
Mandate Chain:
 ├─ IntentMandate (mandate_id=c1b03b47-e649-4b3e-88a9-f2a45a5b16cf, vc_id=urn:uuid:78c12433-5204-4204-87c7-1919b131f170)
    merchant=CNY issuer=issuer:user-wallet exp=2025-10-05T21:57:43Z
 ├─ CartMandate (mandate_id=e716c58e-1dc1-4c34-b648-cb884315aff3, vc_id=urn:uuid:2c467e21-9688-4dea-a862-408709763ccd)
    merchant=CNY issuer=issuer:merchant exp=2025-10-05T21:57:43Z
 ├─ NettingMandate (mandate_id=c5c9fc56-0546-4e89-8b04-a0e600474908, vc_id=urn:uuid:a3f79c45-9176-4427-9ade-cba800312b58)
    merchant=CNY issuer=issuer:netting exp=2025-10-05T21:57:43Z
 └─ PaymentMandate (mandate_id=89f7f94d-a74f-407c-a6f9-4b93928a059c, vc_id=urn:uuid:9c0636ff-4f12-4f99-83f8-23b390c0bd1c)
    merchant=CNY issuer=issuer:processor exp=2025-10-05T21:57:43Z
```

---

#### Fraud Flag

```
flag urn:uuid:9c0636ff-4f12-4f99-83f8-23b390c0bd1c
```

**Produces:**

```
[Agent] Please provide a reason for this fraud initiation: Unauthorized
```

This flags a PaymentMandate as a fraudulent transaction and sends this to the processor to nullify it (0.0 amounts) which then directs it to the merchant / counterparty.

**Output:**

```
TXN fraud-8ccdcb36-b19e-4cf2-856a-87d9d40a5529 | issuer:processor -> CNY 0.0 KRW
Mandate Chain:
 └─ FraudFlag (mandate_id=9643a3aa-573e-4450-b325-9875c057e996, vc_id=urn:uuid:06bc8ed0-ef18-4274-8da3-e99cbc8d0c1c)
    merchant=n/a issuer=issuer:processor exp=2025-10-05T22:02:17Z
```

---

## 🔗 Mandate Chain

Every transaction creates an auditable chain of linked mandates:

1. **IntentMandate** - User initiates payment intent
2. **CartMandate** - Merchant confirms cart details
3. **NettingMandate** (optional) - Settlement netting for corporate banking
4. **PaymentMandate** - Processor finalizes payment
5. **RefundMandate** / **FraudFlag** (optional) - Post-payment actions

Each mandate references the previous mandate via `prev_mandate_id`, creating a complete audit trail.

---

## 📋 Mandate Types

| Mandate Type | Issuer | Purpose |
|-------------|--------|---------|
| **IntentMandate** | User Wallet | Express payment intent |
| **CartMandate** | Merchant | Confirm checkout details |
| **NettingMandate** | Netting Service | EOD batch settlement |
| **PaymentMandate** | Processor | Finalize payment |
| **RefundMandate** | Processor | Issue refund |
| **FraudFlag** | Processor | Flag fraudulent activity |

---

## 🏦 Corporate Banking Integration

The **NettingMandate** enables AP2 to integrate with traditional banking workflows:

- Supports end-of-day (EOD) batch processing
- Settlement run identification (e.g., DTP2)
- Counterparty netting for investment and commercial banking
- Payment execution only after netting completion

This bridges the gap between modern payment protocols and legacy banking infrastructure.

---

## 🔐 Security & Compliance

- All mandates are **W3C Verifiable Credentials**
- Signed with **Ed25519Signature2020**
- Support for **RevocationList2020Status**
- Complete audit trail with timestamp and issuer verification
- Immutable mandate chain with cryptographic linkage

---

## 📝 License

This is a reference implementation for the AP2 protocol. See [ap2-protocol.org](https://ap2-protocol.org/) for specification details.  Source code will be released soon under a business friendly licence.
