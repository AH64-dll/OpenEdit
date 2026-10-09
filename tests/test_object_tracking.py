"""Moving footage, editable motion source, bounded AI context and real masks."""
import json
import subprocess
import time

import numpy as np
import pytest
from PIL import Image, ImageDraw

from open_edit.ir.derive import derive_timeline
from open_edit.ir.object_tracking import ObjectTrack, TrackFrame, sample_track
from open_edit.ir.types import AddClipOp, MoveClipOp, Project, TrimClipOp
from open_edit.kernel.object_tracking import (
    TrackingRequest,
    edit_object_track,
    prepare_tracking,
    track_video,
)
from open_edit.kernel.pillar_tools import dispatch_edit, dispatch_query
from open_edit.kernel.studio_service import commit_studio, get_editing_context
from open_edit.kernel.tracking_jobs import apply_tracking_job, get_tracking_job, start_tracking
from open_edit.render.object_tracking import tracking_overlays
from open_edit.render.pipe_builder import overlay_filter_chain
from open_edit.render.profiles import RenderProfile
from open_edit.storage.assets import AssetStore
from open_edit.storage.edit_graph import EditGraphStore


def position(t):
    return round(20 + 35*t), round(65 + 8*np.sin(t*2))


@pytest.fixture(scope='module')
def video(tmp_path_factory):
    root = tmp_path_factory.mktemp('moving-object')
    path = root / 'moving.mkv'
    process = subprocess.Popen(['ffmpeg', '-v', 'error', '-y', '-f', 'rawvideo', '-pix_fmt', 'rgb24',
        '-s', '320x180', '-r', '15', '-i', '-', '-c:v', 'ffv1', str(path)], stdin=subprocess.PIPE)
    rng = np.random.default_rng(42)
    texture = Image.fromarray(rng.integers(100, 255, size=(36, 48, 3), dtype=np.uint8))
    draw = ImageDraw.Draw(texture)
    draw.rectangle((2, 2, 45, 33), outline='#fff', width=2)
    draw.line((0, 0, 47, 35), fill='#f00', width=3)
    for index in range(60):
        image = Image.new('RGB', (320, 180), '#15202b')
        image.paste(texture, position(index/15))
        process.stdin.write(image.tobytes())
    process.stdin.close()
    assert process.wait(timeout=30) == 0
    return path


@pytest.fixture
def project(tmp_path, video, monkeypatch):
    monkeypatch.setenv('OPEN_EDIT_SOURCE_PROXY_AUTO', '0')
    assets = AssetStore(tmp_path / '.open_edit/assets')
    asset = assets.ingest(str(video), transcribe=False)
    store = EditGraphStore(tmp_path / '.open_edit/edit_graph.db')
    store.append(AddClipOp(author='user', clip_id='hero', asset_hash=asset.asset_hash, track_id='main',
        position_sec=2, in_point_sec=.4, out_point_sec=3.6))
    return tmp_path, store, assets, asset


def request(store, **overrides):
    x, y = position(1.4)
    return TrackingRequest(expected_revision=store.graph_revision(), clip_id='hero', region={
        'left': x, 'top': y, 'right': x+48, 'bottom': y+36, 'canvas_width': 320,
        'canvas_height': 180, 'playhead_sec': 3}, **overrides)


def test_real_tracker_follows_both_directions_on_trimmed_moved_clip(project):
    root, store, _, _ = project
    req = request(store)
    result = track_video(prepare_tracking(root, req), req)
    assert result.frames[0].time_sec == pytest.approx(.4)
    assert result.frames[-1].time_sec == pytest.approx(3.6)
    assert all(f.valid for f in result.frames)
    for t in (.6, 1.4, 2.5, 3.4):
        frame = sample_track(result, t)
        x, y = position(t)
        assert abs(frame.x*320 - x) < 9
        assert abs(frame.y*180 - y) < 9
    assert store.graph_revision() == 1


def manual_track(asset):
    return {'clip_id': 'hero', 'asset_hash': asset.asset_hash, 'frames': [
        {'time_sec': t, 'x': position(t)[0]/320, 'y': position(t)[1]/180, 'width': .15, 'height': .2}
        for t in (.4, 1.4, 2.4, 3.6)]}


def test_small_agent_edits_keep_samples_and_share_locks_history(project):
    root, store, _, asset = project
    commit_studio(root, expected_revision=1, changes=[{'kind': 'object_track', 'object_id': 'target', 'data': manual_track(asset)}])
    revision = store.graph_revision()
    result = dispatch_edit('edit_object_track', {'expected_revision': revision, 'object_id': 'target', 'edits': [
        {'action': 'add_effect', 'effect': {'effect_id': 'blur-1', 'kind': 'blur'}},
        {'action': 'set_frame', 'frame': {'time_sec': 2., 'x': .4, 'y': .4, 'width': .2, 'height': .2}},
    ], 'author': 'user', 'request_id': 'agent-edit'}, root)
    assert result['status'] == 'ok'
    data = store.studio_snapshot('object_track')['objects'][0]['data']
    assert len(data['frames']) == 5 and data['frames'][2]['manual']
    assert store.history()['actions'][0]['author'] == 'ai'
    context = get_editing_context(root, selected_ids=['target'], playhead_sec=3)
    assert 'frames' not in context['object_tracks'][0]['data']
    assert context['object_tracks'][0]['data']['frame_count'] == 5
    assert len(json.dumps(context)) < 9000
    assert context['selected_clips'][0]['clip_id'] == 'hero'
    store.history_step('undo', store.graph_revision())
    assert len(store.studio_snapshot('object_track')['objects'][0]['data']['frames']) == 4
    store.history_step('redo', store.graph_revision())
    edit_object_track(root, expected_revision=store.graph_revision(), object_id='target', edits=[{'action':'properties','values':{'locked':True}}])
    with pytest.raises(ValueError, match=r'locked|Unlock|unlock'):
        edit_object_track(root, expected_revision=store.graph_revision(), object_id='target', edits=[{'action':'remove_effect','effect_id':'blur-1'}])


def test_job_is_durable_and_requires_explicit_application(project):
    root, store, _, _ = project
    result = start_tracking(root, direction='forward', **request(store).model_dump(exclude={'direction'}))
    job_id = result['job']['job_id']
    for _ in range(150):
        job = get_tracking_job(root, job_id=job_id)['job']
        if job['status'] in ('succeeded','failed'):
            break
        time.sleep(.1)
    assert job['status'] == 'succeeded', job
    assert store.graph_revision() == 1
    assert dispatch_query('get_tracking_job', {'job_id': job_id}, root)['job']['track']['frame_count'] > 10
    receipt = apply_tracking_job(root, job_id=job_id, expected_revision=1)
    assert receipt['changed']
    assert EditGraphStore(store.db_path).studio_snapshot('object_track')['objects']
    assert get_tracking_job(root, job_id=job_id)['job']['status'] == 'applied'
    with pytest.raises(ValueError, match='unapplied'):
        apply_tracking_job(root, job_id=job_id, expected_revision=store.graph_revision())


def test_loss_is_not_extrapolated_and_invalid_boxes_rejected():
    track = ObjectTrack(clip_id='a', asset_hash='a'*64, frames=[
        TrackFrame(time_sec=0, x=.1,y=.1,width=.2,height=.2),
        TrackFrame(time_sec=1, x=.2,y=.2,width=.2,height=.2,valid=False),
        TrackFrame(time_sec=2, x=.3,y=.3,width=.2,height=.2,manual=True)])
    assert sample_track(track, .5) is None
    assert sample_track(track, 1.5) is None
    assert sample_track(track, 2).manual
    assert sample_track(track, 3) is None
    with pytest.raises(ValueError):
        TrackFrame(time_sec=0,x=.9,y=0,width=.2,height=.2)


def test_foreground_is_identified_inside_a_loose_region(project):
    root, store, _, _ = project
    req = request(store, direction='forward')
    req.region.left -= 12
    req.region.top -= 12
    req.region.right += 12
    req.region.bottom += 12
    result = track_video(prepare_tracking(root, req), req)
    assert 'GrabCut foreground' in result.algorithm
    first = result.frames[0]
    x,y = position(1.4)
    assert abs(first.x*320-x) < 5 and abs(first.y*180-y) < 5
    assert first.width*320 < 60 and first.height*180 < 48


@pytest.mark.parametrize('edit', [5, {'action':'remove_frame','time_sec':'oops'},
    {'action':'set_frame','frame':[]}, {'action':'properties','values':{'clip_id':'other'}},
    {'action':'update_effect','effect_id':'missing','values':{}},
    {'action':'set_frame','frame':{'time_sec':99,'x':.2,'y':.2,'width':.2,'height':.2}}])
def test_malformed_edits_are_rejected_without_mutation(project, edit):
    root, store, _, asset = project
    commit_studio(root, expected_revision=1, changes=[{'kind':'object_track','object_id':'target','data':manual_track(asset)}])
    revision = store.graph_revision()
    result = dispatch_edit('edit_object_track', {'expected_revision':revision,'object_id':'target','edits':[edit]},root)
    assert result['status'] == 'error'
    assert store.graph_revision() == revision


def test_following_masks_use_source_time_after_move_trim_and_real_ffmpeg(project):
    root, store, assets, asset = project
    data = manual_track(asset)
    data['effects'] = [{'effect_id':'blur-1','kind':'blur','padding':0}]
    commit_studio(root, expected_revision=1, changes=[{'kind':'object_track','object_id':'target','data':data}])
    store.append(MoveClipOp(author='user', clip_id='hero', new_track_id='main', new_position_sec=1))
    store.append(TrimClipOp(author='user', clip_id='hero', new_in_point_sec=1.4, new_out_point_sec=3.4))
    timeline = derive_timeline(Project(name='test', edit_graph=store.load_all()))
    profile = RenderProfile(name='tracking-test',width=320,height=180,frame_rate_num=15,frame_rate_den=1)
    overlays = tracking_overlays(root, timeline, assets, profile)
    assert overlays[0].position_sec == 1 and overlays[0].duration_sec == 2
    mask = subprocess.run(['ffmpeg','-v','error','-i',str(overlays[0].media_path),'-frames:v','1','-f','rawvideo','-pix_fmt','gray','-'],capture_output=True,check=True).stdout
    image = np.frombuffer(mask, np.uint8).reshape(180,320)
    x,y = position(1.4)
    assert image[y+10,x+10] == 255 and image[10,10] == 0
    chain = ';'.join(overlay_filter_chain(overlays,320,180,first_overlay_input=1))
    output = root/'masked.mkv'
    subprocess.run(['ffmpeg','-v','error','-y','-threads','1','-i',str(asset.stored_path),'-i',str(overlays[0].media_path),
        '-filter_complex_threads','1','-filter_complex',chain,'-map','[vout]','-an','-c:v','ffv1',str(output)],check=True,timeout=30)
    info = json.loads(subprocess.run(['ffprobe','-v','error','-show_format','-of','json',str(output)],capture_output=True,check=True).stdout)
    assert float(info['format']['duration']) == pytest.approx(4, abs=.1)


def test_split_and_duplicate_keep_independently_editable_tracks_and_atomic_undo(project):
    root, store, _, asset = project
    data = manual_track(asset)
    data['effects'] = [{'effect_id':'box-1','kind':'highlight'}]
    commit_studio(root, expected_revision=1, changes=[{'kind':'object_track','object_id':'target','data':data}])
    revision = store.graph_revision()
    receipt = commit_studio(root, expected_revision=revision, changes=[], ops=[
        {'kind':'split_clip','clip_id':'hero','at_sec':3.5,'left_clip_id':'left','right_clip_id':'right'}])
    objects = store.studio_snapshot('object_track')['objects']
    assert len(objects) == 2
    assert next(o for o in objects if o['object_id']=='target')['data']['clip_id'] == 'left'
    copy = next(o for o in objects if o['data']['clip_id']=='right')
    assert copy['data']['effects'][0]['effect_id'] != 'box-1'
    store.history_step('undo', receipt['graph_revision'])
    assert store.studio_snapshot('object_track')['objects'][0]['data']['clip_id'] == 'hero'
    assert len(store.studio_snapshot('object_track')['objects']) == 1
    commit_studio(root, expected_revision=store.graph_revision(), changes=[], ops=[
        {'kind':'duplicate_clip','clip_id':'hero','new_clip_id':'copy','position_sec':6}])
    objects = store.studio_snapshot('object_track')['objects']
    assert len(objects) == 2
    duplicate = next(o for o in objects if o['data']['clip_id']=='copy')
    edit_object_track(root, expected_revision=store.graph_revision(), object_id=duplicate['object_id'],
        edits=[{'action':'update_effect','effect_id':duplicate['data']['effects'][0]['effect_id'],'values':{'color':'#ff0000'}}])
    original = next(o for o in store.studio_snapshot('object_track')['objects'] if o['object_id']=='target')
    assert original['data']['effects'][0]['color'] == '#ffcc55'


def test_tracking_change_only_dirties_affected_video_chunks(project):
    from open_edit.render.preview_invalidation import compute_chunk_fingerprints, make_chunk_windows

    root, store, _, asset = project
    data = manual_track(asset)
    data['effects'] = [{'effect_id':'box-1','kind':'highlight'}]
    commit_studio(root, expected_revision=1, changes=[{'kind':'object_track','object_id':'target','data':data}])
    old = derive_timeline(Project(name='test',edit_graph=store.load_all()))
    edit_object_track(root, expected_revision=store.graph_revision(), object_id='target', edits=[
        {'action':'set_frame','frame':{'time_sec':2.,'x':.5,'y':.4,'width':.15,'height':.2}}])
    new = derive_timeline(Project(name='test',edit_graph=store.load_all()))
    windows = make_chunk_windows(180,30,1)
    before = compute_chunk_fingerprints(old_timeline=None,new_timeline=old,windows=windows,old_graph_hash=None,
        new_graph_hash='old',operations=[],profile_fingerprint='fixed',content_fingerprint='fixed')
    after = compute_chunk_fingerprints(old_timeline=old,new_timeline=new,windows=windows,old_graph_hash='old',
        new_graph_hash='new',operations=[],profile_fingerprint='fixed',content_fingerprint='fixed')
    assert [c.audio_key for c in before] == [c.audio_key for c in after]
    assert before[0].video_key == after[0].video_key
    assert before[3].video_key != after[3].video_key


def test_tracker_reports_real_occlusion_instead_of_switching_to_background(project):
    root, store, _, _ = project
    req = request(store, direction='forward', target_mode='region')
    prepared = prepare_tracking(root, req)
    occluded = root/'occluded.mkv'
    subprocess.run(['ffmpeg','-v','error','-y','-i',prepared['path'],'-vf',
        "drawbox=x=0:y=0:w=iw:h=ih:color=0x15202b:t=fill:enable='gte(t,2)'",'-c:v','ffv1',str(occluded)],check=True,timeout=30)
    prepared['path'] = str(occluded)
    result = track_video(prepared, req)
    assert any(not f.valid for f in result.frames if f.time_sec > 2.1)
    assert sample_track(result, 3) is None
    from open_edit.kernel.object_tracking import summarize_track

    summary = summarize_track(result.model_dump(mode='json'))
    assert summary['lost_ranges'][0][0] >= 1.9
    assert summary['lost_ranges'][0][1] == pytest.approx(3.6)


def test_cancelled_tracking_creates_no_edit(project, monkeypatch):
    import threading

    from open_edit.kernel import tracking_jobs

    root, store, _, _ = project
    running = threading.Event()
    def fake_track(prepared, request, *, cancelled, progress):
        running.set()
        for _ in range(100):
            if cancelled():
                raise InterruptedError('Tracking cancelled')
            time.sleep(.01)
        raise AssertionError('Cancellation was not delivered')
    monkeypatch.setattr(tracking_jobs, 'track_video', fake_track)
    result = start_tracking(root, **request(store).model_dump())
    job_id = result['job']['job_id']
    assert running.wait(timeout=2)
    tracking_jobs.cancel_tracking(root, job_id=job_id)
    for _ in range(100):
        job = get_tracking_job(root, job_id=job_id)['job']
        if job['status'] == 'cancelled':
            break
        time.sleep(.01)
    assert job['status'] == 'cancelled'
    assert store.graph_revision() == 1
    assert not store.studio_snapshot('object_track')['objects']


def test_completed_job_cannot_overwrite_a_concurrent_track_edit(project, monkeypatch):
    from open_edit.kernel import tracking_jobs

    root, store, _, asset = project
    commit_studio(root, expected_revision=1, changes=[{'kind':'object_track','object_id':'target','data':manual_track(asset)}])
    monkeypatch.setattr(tracking_jobs, 'track_video', lambda *args, **kwargs: ObjectTrack.model_validate(manual_track(asset)))
    job_id = start_tracking(root, **request(store, object_id='target').model_dump())['job']['job_id']
    for _ in range(100):
        if get_tracking_job(root, job_id=job_id)['job']['status'] == 'succeeded':
            break
        time.sleep(.01)
    edit_object_track(root, expected_revision=store.graph_revision(), object_id='target',
        edits=[{'action':'properties','values':{'label':'Manual correction'}}])
    revision = store.graph_revision()
    with pytest.raises(ValueError, match='changed while tracking'):
        apply_tracking_job(root, job_id=job_id, expected_revision=revision)
    assert store.graph_revision() == revision
    assert store.studio_snapshot('object_track')['objects'][0]['data']['label'] == 'Manual correction'


def test_long_track_context_is_small_and_loss_ranges_are_bounded(project):
    root, _store, _, asset = project
    data = manual_track(asset)
    data['frames'] = [{'time_sec':i/3000,'x':.1,'y':.2,'width':.2,'height':.2,'valid':i%20 != 0} for i in range(9001)]
    commit_studio(root, expected_revision=1, changes=[{'kind':'object_track','object_id':'target','data':data}])
    context = get_editing_context(root,selected_ids=['target'])
    summary = context['object_tracks'][0]['data']
    assert summary['frame_count'] == 9001
    assert summary['lost_range_count'] > 10 and len(summary['lost_ranges']) == 10
    assert len(json.dumps(context)) < 7000


def test_ai_request_revert_preserves_later_effect_and_frame_properties(project):
    from open_edit.kernel.request_history import revert_request

    root, store, _, asset = project
    data = manual_track(asset)
    data['effects'] = [{'effect_id':'box','kind':'highlight'}]
    commit_studio(root, expected_revision=1, changes=[{'kind':'object_track','object_id':'target','data':data}])
    edit_object_track(root, expected_revision=store.graph_revision(), object_id='target', author='ai', request_id='edit', edits=[
        {'action':'update_effect','effect_id':'box','values':{'color':'#ff0000'}},
        {'action':'set_frame','frame':{**data['frames'][1],'x':.5}}])
    edit_object_track(root, expected_revision=store.graph_revision(), object_id='target', edits=[
        {'action':'update_effect','effect_id':'box','values':{'padding':.05}},
        {'action':'set_frame','frame':{**data['frames'][2],'y':.5}}])
    result = revert_request(root, request_id='edit', expected_revision=store.graph_revision())
    assert result['changed'], result
    source = store.studio_snapshot('object_track')['objects'][0]['data']
    assert source['effects'][0]['color'] == '#ffcc55' and source['effects'][0]['padding'] == .05
    assert source['frames'][1]['x'] == data['frames'][1]['x'] and source['frames'][2]['y'] == .5
    timeline = derive_timeline(Project(name='test',edit_graph=store.load_all()),strict=True)
    assert timeline.object_tracks['target'].model_dump(mode='json') == source


@pytest.mark.parametrize('kind',['split_clip','duplicate_clip'])
def test_ai_split_or_copy_can_be_selectively_reverted_and_undone(project, kind):
    from open_edit.kernel.request_history import revert_request

    root, store, _, asset = project
    commit_studio(root, expected_revision=1, changes=[{'kind':'object_track','object_id':'target','data':manual_track(asset)}])
    raw = {'kind':kind,'clip_id':'hero'}
    raw.update({'at_sec':3.5,'left_clip_id':'left','right_clip_id':'right'} if kind == 'split_clip'
               else {'new_clip_id':'copy','position_sec':6})
    commit_studio(root, expected_revision=store.graph_revision(), changes=[], ops=[raw], author='ai',request_id='copy')
    result = revert_request(root,request_id='copy',expected_revision=store.graph_revision())
    assert result['changed'], result
    objects = store.studio_snapshot('object_track')['objects']
    assert len(objects) == 1 and objects[0]['data']['clip_id'] == 'hero'
    timeline = derive_timeline(Project(name='test',edit_graph=store.load_all()),strict=True)
    assert list(timeline.object_tracks) == ['target']
    store.history_step('undo', store.graph_revision())
    assert len(store.studio_snapshot('object_track')['objects']) == 2


def test_stale_tracks_do_not_block_splitting_a_replaced_source(project):
    from open_edit.ir.types import ReplaceClipSourceOp, SplitClipOp

    root, store, _, asset = project
    commit_studio(root, expected_revision=1, changes=[{'kind':'object_track','object_id':'target','data':manual_track(asset)}])
    store.append(ReplaceClipSourceOp(author='user',clip_id='hero',new_asset_hash='b'*64))
    store.append(SplitClipOp(author='user',clip_id='hero',at_sec=3.5,left_clip_id='left',right_clip_id='right'))
    assert len(store.studio_snapshot('object_track')['objects']) == 1


def test_job_liveness_checks_do_not_terminate_a_live_process():
    import sys

    from open_edit.kernel.tracking_jobs import _process_alive

    child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'])
    try:
        assert _process_alive(child.pid)
        assert child.poll() is None
    finally:
        child.terminate()
        child.wait(timeout=5)
    assert not _process_alive(child.pid)


def test_retracking_preserves_manual_name_disabled_state_and_effects(project):
    root, store, _, asset = project
    data = manual_track(asset)
    data.update(label='My selected object',enabled=False,effects=[{'effect_id':'box','kind':'highlight'}])
    commit_studio(root,expected_revision=1,changes=[{'kind':'object_track','object_id':'target','data':data}])
    req = request(store,object_id='target',direction='forward')
    prepared = prepare_tracking(root,req)
    # Durable jobs serialize the request including defaults; prepared metadata
    # still distinguishes an omitted name from an explicit rename.
    result = track_video(prepared,TrackingRequest.model_validate(req.model_dump()))
    assert result.label == 'My selected object' and result.enabled is False
    assert result.effects[0].effect_id == 'box'
    assert result.frames[0].time_sec == .4


def test_reverting_clip_creator_tolerates_historical_object_track(project):
    # CORE-02: derive replay must skip a SetObjectTrackOp whose historical
    # clip no longer exists (creator reverted), like every other dependent
    # op family — reverting the clip creator used to brick derivation.
    from open_edit.ir.apply import apply_operation
    from open_edit.ir.types import Timeline

    root, store, _, asset = project
    commit_studio(root, expected_revision=1, changes=[
        {'kind': 'object_track', 'object_id': 'target', 'data': manual_track(asset)}])
    creator = next(op for op in store.load_all() if op.kind == 'add_clip')
    raw = store.load_all()
    set_op = raw[-1]
    assert set_op.kind == 'set_object_track'
    # Direct low-level revert of the creator (no parent chain between them):
    store.update_status(creator.edit_id, 'reverted')
    timeline = derive_timeline(Project(name='core02', edit_graph=store.load_all()))
    assert [c.clip_id for t in timeline.tracks for c in t.clips] == []
    # The historical track is not re-materialized onto a missing clip.
    assert 'target' not in timeline.object_tracks
    # Explicit strict=True still rejects the missing-clip reference.
    with pytest.raises(Exception, match="not found in timeline"):
        apply_operation(Timeline(), set_op, strict=True)


def test_unreverting_creator_restores_track_and_mismatch_still_rejects(project):
    # CORE-02: only the MISSING-clip case is tolerant; a clip that IS
    # resolved still enforces the asset/video-kind track constraints.
    from open_edit.ir.apply import apply_operation
    from open_edit.ir.object_tracking import ObjectTrack, TrackFrame
    from open_edit.ir.types import SetObjectTrackOp, Timeline

    root, store, _, asset = project
    commit_studio(root, expected_revision=1, changes=[
        {'kind': 'object_track', 'object_id': 'target', 'data': manual_track(asset)}])
    creator = next(op for op in store.load_all() if op.kind == 'add_clip')
    set_op = next(op for op in store.load_all() if op.kind == 'set_object_track')
    store.update_status(creator.edit_id, 'reverted')
    store.update_status(creator.edit_id, 'applied')
    timeline = derive_timeline(Project(name='core02b', edit_graph=store.load_all()))
    assert timeline.object_tracks['target'].clip_id == creator.clip_id

    live = apply_operation(Timeline(), creator)
    mismatched = SetObjectTrackOp(author='user', object_id='mismatch', clip_id=creator.clip_id,
        track=ObjectTrack(clip_id=creator.clip_id, asset_hash='f'*64, frames=[
            TrackFrame(time_sec=creator.in_point_sec, x=.1, y=.1, width=.2, height=.2)]))
    with pytest.raises(Exception, match='original video clip and asset'):
        apply_operation(live.model_copy(deep=True), mismatched)
