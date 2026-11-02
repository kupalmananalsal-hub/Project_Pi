"""Package existing ONNX artifacts only; no inference, training or deployment.

The small protobuf reader inspects tensor metadata without installing ONNX.
Runtime compatibility still requires the operator's existing openWakeWord/ORT.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil


def fields(data):
    def varint(offset):
        value = 0
        for shift in range(0, 70, 7):
            byte = data[offset]
            offset += 1
            value |= (byte & 127) << shift
            if byte < 128:
                return value, offset
        raise ValueError('oversized protobuf integer')

    offset = 0
    while offset < len(data):
        tag, offset = varint(offset)
        wire = tag & 7
        if wire == 0:
            value, offset = varint(offset)
        elif wire == 2:
            size, offset = varint(offset)
            if size > len(data) - offset:
                raise ValueError('truncated protobuf field')
            value = data[offset:offset + size]
            offset += size
        elif wire in (1, 5):
            size = 8 if wire == 1 else 4
            value = data[offset:offset + size]
            offset += size
            if len(value) != size:
                raise ValueError('truncated protobuf field')
        else:
            raise ValueError('unsupported protobuf wire type')
        yield tag >> 3, value


def tensors(graph, number):
    result = []
    for field, value in fields(graph):
        if field != number:
            continue
        info = dict(fields(value))
        tensor = dict(fields(dict(fields(info[2]))[1]))
        shape = []
        for _, dim in fields(tensor.get(2, b'')):
            dimension = dict(fields(dim))
            shape.append(dimension.get(1, dimension.get(2, b'?').decode()))
        result.append(dict(name=info[1].decode(), element_type=tensor[1], shape=shape))
    return result


def package(source, output):
    source = source.resolve(strict=True)
    models = sorted(source.glob('*.onnx'))
    if not models:
        raise ValueError('no ONNX artifacts found')
    inventory = []
    approved = []
    for model in models:
        if model.is_symlink() or model.stat().st_size > 64 * 1024 * 1024:
            raise ValueError(f'unsafe or oversized artifact: {model.name}')
        graph = dict(fields(model.read_bytes()))[7]
        inputs, outputs = tensors(graph, 11), tensors(graph, 12)
        companions = set()
        for number, tensor in fields(graph):
            if number != 5:
                continue
            for key, entry in fields(tensor):
                if key == 13:
                    metadata = dict(fields(entry))
                    if metadata[1] == b'location':
                        location = metadata[2].decode()
                        if location != model.name + '.data':
                            raise ValueError(f'unsupported external data location: {model.name}')
                        companions.add(source / location)
        files = [model, *sorted(companions)]
        for path in files:
            if not path.is_file() or path.is_symlink():
                raise ValueError(f'missing or unsafe companion: {path.name}')
        candidate = (len(inputs) == 1 and inputs[0]['element_type'] == 1
                     and len(inputs[0]['shape']) == 3 and inputs[0]['shape'][-1] == 96
                     and len(outputs) == 1 and outputs[0]['shape'][-1:] == [1])
        inventory.append(dict(model=model.name, inputs=inputs, outputs=outputs,
            status='EMBEDDING_CLASSIFIER_CANDIDATE' if candidate else 'REQUIRES_COMPATIBILITY_REVIEW',
            runtime_compatibility='NOT_EXECUTED', files=[dict(name=p.name, bytes=p.stat().st_size,
                sha256=hashlib.file_digest(p.open('rb'), 'sha256').hexdigest()) for p in files]))
        if candidate:
            approved.extend(files)
    output.mkdir(parents=True, exist_ok=False)
    destination = output / 'models'
    destination.mkdir()
    for path in approved:
        shutil.copy2(path, destination / path.name)
    (output / 'model_inventory.json').write_text(json.dumps(inventory, indent=2) + '\n', encoding='utf-8')
    print(f'Inspected {len(models)} models; packaged {len(approved)} artifact files; no inference performed.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    package(args.source, args.output)
