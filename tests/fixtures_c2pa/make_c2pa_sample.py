"""Create tests/samples/c2pa_ai.jpg: a JPEG carrying a C2PA manifest that
declares it was made by a generative AI model (digitalSourceType =
trainedAlgorithmicMedia). Signed with the TEST-ONLY certificates in this
folder; they have no value outside the test-suite.
"""

import io
import json
from pathlib import Path

import c2pa

HERE = Path(__file__).parent
SAMPLES = HERE.parent / "samples"

manifest = {
    "claim_generator_info": [{"name": "TestDiffusion", "version": "1.0"}],
    "title": "c2pa_ai.jpg",
    "format": "image/jpeg",
    "assertions": [
        {
            "label": "c2pa.actions",
            "data": {
                "actions": [
                    {
                        "action": "c2pa.created",
                        "digitalSourceType": "http://cv.iptc.org/newscodes/digitalsourcetype/trainedAlgorithmicMedia",
                        "softwareAgent": {"name": "TestDiffusion 1.0"},
                    }
                ]
            },
        }
    ],
}

info = c2pa.C2paSignerInfo(
    alg=b"es256",
    sign_cert=(HERE / "chain.pem").read_bytes(),
    private_key=(HERE / "leaf.key").read_bytes(),
    ta_url=None,
)
signer = c2pa.Signer.from_info(info)
builder = c2pa.Builder(json.dumps(manifest))
src = io.BytesIO((SAMPLES / "sample.jpg").read_bytes())
dst = io.BytesIO()
builder.sign(signer, "image/jpeg", src, dst)
(SAMPLES / "c2pa_ai.jpg").write_bytes(dst.getvalue())
print("wrote", SAMPLES / "c2pa_ai.jpg")
