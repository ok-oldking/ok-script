import json
import os
from pathlib import Path

import cv2
import numpy as np
import pytest

from ok.feature.FeatureSet import FeatureSet, generate_templates, crop_filename, read_feature_crops, read_from_json


def test_export_and_load_individual_features_without_coco(tmp_path):
    source = tmp_path / 'source'
    source.mkdir()
    pixels = np.arange(20 * 30 * 3, dtype=np.uint8).reshape(20, 30, 3)
    assert cv2.imwrite(str(source / 'screen.png'), pixels)
    data = {'images': [{'id': 1, 'file_name': 'screen.png', 'width': 30, 'height': 20}],
            'categories': [{'id': 1, 'name': '保存_a'}, {'id': 2, 'name': 'box_area'}],
            'annotations': [{'image_id': 1, 'category_id': 1, 'bbox': [3, 4, 5, 6]},
                            {'image_id': 1, 'category_id': 2, 'bbox': [15, 8, 4, 3]}]}
    source_json = source / 'coco_annotations.json'
    source_json.write_text(json.dumps(data), encoding='utf-8')
    target = tmp_path / 'assets'
    key = generate_templates(str(source_json), str(target), str(source))
    assert Path(key).is_dir()
    assert source_json.exists()
    assert (source / 'screen.png').exists()
    assert not list(target.glob('*.json'))
    files = sorted(target.glob('*.png'))
    assert len(files) == 2
    crop = target / crop_filename('保存_a', 30, 20, 3, 4)
    assert crop.name == '保存_a_30x20_3_4.png'
    np.testing.assert_array_equal(cv2.imdecode(np.fromfile(crop, dtype=np.uint8), cv2.IMREAD_COLOR), pixels[4:10, 3:8])
    features, boxes, compressed, success, _ = read_feature_crops(key, 60, 40)
    assert success and compressed
    assert (boxes['保存_a'].x, boxes['保存_a'].y, boxes['保存_a'].width, boxes['保存_a'].height) == (6, 8, 10, 12)
    assert np.all(features['box_area'].mat == 255)
    only, _, _, _, _ = read_feature_crops(key, target_category_name='保存_a')
    assert list(only) == ['保存_a']
    fs = FeatureSet(False, None, 0, 0, template_folder=key)
    assert fs.check_size(np.zeros((40, 60, 3), dtype=np.uint8))
    assert fs.get_box_by_name(np.zeros((40, 60, 3), dtype=np.uint8), '保存_a').x == 6
    before = {p.name: p.read_bytes() for p in files}
    generate_templates(str(source_json), str(target), str(source))
    assert before == {p.name: p.read_bytes() for p in target.glob('*.png')}


def test_failed_export_preserves_existing_assets(tmp_path):
    source = tmp_path / 'source'
    source.mkdir()
    cv2.imwrite(str(source / 'screen.png'), np.zeros((10, 10, 3), dtype=np.uint8))
    data = {'images': [{'id': 1, 'file_name': 'screen.png'}],
            'categories': [{'id': 1, 'name': 'a'}],
            'annotations': [{'image_id': 1, 'category_id': 1, 'bbox': [1, 1, 3, 3]}]}
    path = source / 'coco.json'
    target = tmp_path / 'assets'
    path.write_text(json.dumps(data), encoding='utf-8')
    generate_templates(str(path), str(target), str(source))
    before = {p.name: p.read_bytes() for p in target.glob('*.png')}
    data['annotations'][0]['bbox'] = [9, 9, 4, 4]
    path.write_text(json.dumps(data), encoding='utf-8')
    with pytest.raises(ValueError):
        generate_templates(str(path), str(target), str(source))
    assert before == {p.name: p.read_bytes() for p in target.glob('*.png')}


def test_legacy_coco_still_loads_and_scales(tmp_path):
    pixels = np.arange(20 * 30 * 3, dtype=np.uint8).reshape(20, 30, 3)
    cv2.imwrite(str(tmp_path / 'screen.png'), pixels)
    data = {'images': [{'id': 1, 'file_name': 'screen.png'}],
            'categories': [{'id': 1, 'name': 'legacy'}],
            'annotations': [{'image_id': 1, 'category_id': 1, 'bbox': [3, 4, 5, 6]}]}
    path = tmp_path / 'coco.json'
    path.write_text(json.dumps(data), encoding='utf-8')
    features, boxes, _, success, _ = read_from_json(str(path), 60, 40)
    assert success
    assert (boxes['legacy'].x, boxes['legacy'].y, boxes['legacy'].width, boxes['legacy'].height) == (6, 8, 10, 12)
    np.testing.assert_array_equal(features['legacy'].mat, cv2.resize(pixels[4:10, 3:8], (10, 12)))


def _dataset(folder, labels=('old', 'shared'), value=15):
    folder.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(folder / 'screen.png'), np.full((20, 30, 3), value, dtype=np.uint8))
    data = {'images': [{'id': 1, 'file_name': 'screen.png', 'width': 30, 'height': 20}],
            'categories': [{'id': i, 'name': name} for i, name in enumerate(labels)],
            'annotations': [{'image_id': 1, 'category_id': i, 'bbox': [i * 6, 4, 5, 6]}
                            for i, _ in enumerate(labels)]}
    path = folder / 'coco_annotations.json'
    path.write_text(json.dumps(data), encoding='utf-8')
    return path, data


def test_both_sources_preserve_split_priority_with_lazy_coco_preloading(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    legacy, _ = _dataset(tmp_path / 'assets')
    source, _ = _dataset(tmp_path / 'source', ('shared', 'new'), value=83)
    folder = generate_templates(str(source), str(tmp_path / 'templates'))
    calls = []
    fs = FeatureSet(False, str(legacy), 0, 0, template_folder=folder,
                    feature_processor=lambda name, feature: calls.append(name))
    frame = np.zeros((40, 60, 3), dtype=np.uint8)
    assert fs.get_feature_by_name(frame, 'old').mat[0, 0, 0] == 15
    # The first lookup also cached shared from the same legacy image.
    assert fs.get_feature_by_name(frame, 'shared').mat[0, 0, 0] == 83
    assert fs.get_feature_by_name(frame, 'new').mat[0, 0, 0] == 83
    assert sorted(calls) == ['new', 'old', 'shared']
    assert fs.process_data()
    assert fs.feature_dict['shared'].mat[0, 0, 0] == 83


def test_custom_and_imported_templates_load_without_main_coco(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    source, _ = _dataset(tmp_path / 'source', ('button',))
    generate_templates(str(source), str(tmp_path / 'ok_tasks' / 'assets' / 'templates'))
    generate_templates(str(source), str(tmp_path / 'ok_import' / 'module' / 'assets' / 'templates'))
    fs = FeatureSet(False, None, 0, 0)
    frame = np.zeros((20, 30, 3), dtype=np.uint8)
    assert fs.check_size(frame)
    assert fs.get_box_by_name(frame, 'button').name == 'button'
    assert fs.get_box_by_name(frame, 'module/button').name == 'module/button'


def test_regeneration_removes_stale_crops(tmp_path):
    source, data = _dataset(tmp_path / 'source')
    target = tmp_path / 'templates'
    generate_templates(str(source), str(target))
    old_crop = target / crop_filename('old', 30, 20, 0, 4)
    shared_crop = target / crop_filename('shared', 30, 20, 6, 4)
    shared_before = shared_crop.read_bytes()
    data['annotations'] = data['annotations'][1:]
    source.write_text(json.dumps(data), encoding='utf-8')
    generate_templates(str(source), str(target))
    assert not old_crop.exists()
    assert shared_crop.read_bytes() == shared_before


def test_conflicting_sizes_for_same_name_are_rejected_before_replacing(tmp_path):
    source, data = _dataset(tmp_path / 'source', ('same',))
    target = tmp_path / 'templates'
    generate_templates(str(source), str(target))
    before = {p.name: p.read_bytes() for p in target.glob('*.png')}
    data['annotations'].append({'image_id': 1, 'category_id': 0, 'bbox': [0, 4, 4, 6]})
    source.write_text(json.dumps(data), encoding='utf-8')
    with pytest.raises(ValueError, match='Multiple boxes'):
        generate_templates(str(source), str(target))
    assert before == {p.name: p.read_bytes() for p in target.glob('*.png')}


@pytest.mark.parametrize('frame_size', [(50, 20), (30, 40)])
def test_split_preserves_explicit_center_anchors(tmp_path, frame_size):
    source, _ = _dataset(tmp_path / 'source', ('button',))
    folder = generate_templates(str(source), str(tmp_path / 'templates'))
    options = dict(width=frame_size[0], height=frame_size[1],
                   hcenter_features=['button'], vcenter_features=['button'])
    expected_features, expected_boxes, *_ = read_from_json(str(source), **options)
    features, boxes, *_ = read_feature_crops(folder, **options)
    assert (boxes['button'].x, boxes['button'].y) == (expected_boxes['button'].x, expected_boxes['button'].y)
    np.testing.assert_array_equal(features['button'].mat, expected_features['button'].mat)


def test_readable_name_with_spaces_and_geometry_like_suffix_round_trips(tmp_path):
    name = 'save button_1920x1080_10_20'
    source, _ = _dataset(tmp_path / 'source', (name,))
    target = tmp_path / 'templates'
    generate_templates(str(source), str(target))
    assert [p.name for p in target.iterdir()] == [f'{name}_30x20_0_4.png']
    features, boxes, *_ = read_feature_crops(str(target))
    assert list(features) == [name]
    assert (boxes[name].x, boxes[name].y) == (0, 4)


@pytest.mark.parametrize('filename', ['notes.txt', 'unrelated.png', 'button_0x20_0_4.png',
                                      'button_30x20_-1_4.png', 'button_30x20_30_4.png'])
def test_invalid_filename_fails_lazy_load_and_export_without_changing_files(tmp_path, filename):
    source, _ = _dataset(tmp_path / 'source')
    target = tmp_path / 'templates'
    generate_templates(str(source), str(target))
    (target / filename).write_bytes(b'unrelated file')
    before = {p.name: p.read_bytes() for p in target.iterdir()}
    with pytest.raises(ValueError) as error:
        read_feature_crops(str(target), target_category_name='old')
    assert filename in str(error.value)
    with pytest.raises(ValueError) as error:
        generate_templates(str(source), str(target))
    assert filename in str(error.value)
    assert before == {p.name: p.read_bytes() for p in target.iterdir()}


@pytest.mark.parametrize('name', ['bad/name', r'bad\name', 'bad:name', 'bad*name', 'CON.foo'])
def test_filename_unsafe_original_name_is_rejected_without_encoding(tmp_path, name):
    source, _ = _dataset(tmp_path / 'source', (name,))
    target = tmp_path / 'templates'
    with pytest.raises(ValueError, match='Invalid template filename'):
        generate_templates(str(source), str(target))
    assert not list(target.iterdir())


def test_invalid_custom_template_reports_error_to_caller(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    target = tmp_path / 'ok_tasks' / 'assets' / 'templates'
    target.mkdir(parents=True)
    (target / 'bad.png').write_bytes(b'bad')
    features = FeatureSet(False, None, 0, 0)
    with pytest.raises(ValueError, match='bad.png'):
        features.process_data('some_feature')


@pytest.mark.skipif(os.name != 'nt', reason='Windows ACL regression')
def test_export_inherits_destination_permissions_even_when_replacing_private_files(tmp_path):
    import tempfile

    import ntsecuritycon
    import win32security

    source, _ = _dataset(tmp_path / 'source')
    target = tmp_path / 'templates'
    target.mkdir()
    users = win32security.CreateWellKnownSid(win32security.WinBuiltinUsersSid, None)
    security = win32security.GetNamedSecurityInfo(
        str(target), win32security.SE_FILE_OBJECT, win32security.DACL_SECURITY_INFORMATION)
    dacl = security.GetSecurityDescriptorDacl()
    dacl.AddAccessAllowedAceEx(
        win32security.ACL_REVISION,
        win32security.OBJECT_INHERIT_ACE | win32security.CONTAINER_INHERIT_ACE,
        ntsecuritycon.FILE_GENERIC_READ, users)
    win32security.SetNamedSecurityInfo(
        str(target), win32security.SE_FILE_OBJECT, win32security.DACL_SECURITY_INFORMATION,
        None, None, dacl, None)
    # Reproduce an existing export moved from a private staging directory.
    with tempfile.TemporaryDirectory(dir=target) as stage:
        private_file = Path(stage) / crop_filename('old', 30, 20, 0, 4)
        private_file.write_bytes(b'old export')
        os.replace(private_file, target / private_file.name)

    generate_templates(str(source), str(target))

    for path in target.glob('*.png'):
        dacl = win32security.GetNamedSecurityInfo(
            str(path), win32security.SE_FILE_OBJECT,
            win32security.DACL_SECURITY_INFORMATION).GetSecurityDescriptorDacl()
        assert any(
            sid == users and flags & win32security.INHERITED_ACE
            and mask & ntsecuritycon.FILE_GENERIC_READ == ntsecuritycon.FILE_GENERIC_READ
            for (ace_type, flags), mask, sid in (dacl.GetAce(i) for i in range(dacl.GetAceCount()))
        ), f'{path.name} did not inherit read access from the export folder'
        assert cv2.imread(str(path)) is not None
    assert not list(target.glob('.ok-template-*'))
