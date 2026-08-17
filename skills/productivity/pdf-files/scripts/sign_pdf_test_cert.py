#!/usr/bin/env python3
"""Sign a PDF with a short-lived self-signed test certificate."""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import NameOID
from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
from pyhanko.sign import signers


def make_test_pkcs12(common_name: str, passphrase: bytes) -> bytes:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)])
    now = datetime.now(timezone.utc)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(now + timedelta(days=1))
        .sign(key, hashes.SHA256())
    )
    return pkcs12.serialize_key_and_certificates(
        name=common_name.encode("utf-8"),
        key=key,
        cert=certificate,
        cas=None,
        encryption_algorithm=serialization.BestAvailableEncryption(passphrase),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_pdf", type=Path)
    parser.add_argument("output_pdf", type=Path)
    parser.add_argument("--field-name", default="TestSignature")
    parser.add_argument("--reason", default="Test digital signature")
    parser.add_argument("--common-name", default="Hermes PDF Test Signer")
    args = parser.parse_args()

    passphrase = b"changeit"
    p12_data = make_test_pkcs12(args.common_name, passphrase)
    signer = signers.SimpleSigner.load_pkcs12_data(p12_data, other_certs=[], passphrase=passphrase)
    metadata = signers.PdfSignatureMetadata(field_name=args.field_name, reason=args.reason)

    args.output_pdf.parent.mkdir(parents=True, exist_ok=True)
    with args.input_pdf.open("rb") as input_pdf, args.output_pdf.open("wb") as output_pdf:
        writer = IncrementalPdfFileWriter(input_pdf)
        signers.sign_pdf(writer, signature_meta=metadata, signer=signer, output=output_pdf)
    print(f"signed PDF: {args.output_pdf} field={args.field_name}")


if __name__ == "__main__":
    main()
