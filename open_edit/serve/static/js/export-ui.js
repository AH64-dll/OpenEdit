/* Configurable local export from one captured source revision. */
import { state } from './state.js';
import { showToast } from './dom.js';
let dialog,
  project,
  revision,
  model,
  defaults,
  activeJob,
  busy = false,
  loading = false,
  pollGeneration = 0;
const fields = new Map();
const node = (tag, text, attrs = {}) => {
  const n = document.createElement(tag);
  if (text !== undefined) n.textContent = text;
  for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, v);
  return n;
};
const safe = fn => async (...args) => {
  try {
    await fn(...args);
  } catch (error) {
    status(error.message, true);
  }
};
async function request(suffix, body, captured = project) {
  const response = await fetch(`/api/projects/${encodeURIComponent(captured)}${suffix}`, body === undefined ? {} : {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify(body)
  });
  const data = await response.json();
  if (!response.ok) throw new Error(typeof data.error === 'string' ? data.error : typeof data.detail === 'string' ? data.detail : 'Export request failed');
  return data;
}
function status(text, error = false) {
  const el = dialog.querySelector('#export-status');
  el.textContent = text;
  el.classList.toggle('export-error', error);
}
function button(text, fn, attrs = {}) {
  const b = node('button', text, {
    type: 'button',
    class: 'btn btn-secondary btn-sm',
    ...attrs
  });
  b.addEventListener('click', safe(fn));
  return b;
}
function field(section, key, label, options, attrs = {}) {
  const numeric = typeof model[key] === 'number',
    check = typeof model[key] === 'boolean';
  const wrap = node('label', label, check ? { class: 'export-check' } : {}),
    el = node(options ? 'select' : 'input', undefined, {
      name: key,
      ...(!options ? {
        type: check ? 'checkbox' : numeric ? 'number' : 'text'
      } : {}),
      ...attrs
    });
  if (options) for (const option of options) {
    const [value, text] = Array.isArray(option) ? option : [option, option];
    el.append(node('option', text, {
      value
    }));
  }
  if (check) el.checked = model[key];else el.value = model[key] ?? '';
  el.addEventListener(options ? 'change' : 'input', () => {
    model[key] = check ? el.checked : numeric ? Number(el.value) : el.value;
    if (key === 'container') {
      if (model.container === 'webm') {
        model.codec = 'av1';
        model.audio_codec = 'opus';
        model.audio_sample_rate = 48000;
      }
      if (['mp4', 'mov'].includes(model.container)) {
        model.audio_codec = 'aac';
        if (model.container === 'mov' && model.codec === 'av1') model.codec = 'h264';
      }
      for (const k of ['codec', 'audio_codec', 'audio_sample_rate']) fields.get(k).value = model[k];
    }
    if (key === 'audio_codec' && model.audio_codec === 'opus') {
      model.audio_sample_rate = 48000;
      fields.get('audio_sample_rate').value = 48000;
    }
    refresh();
  });
  wrap.append(el);
  section.append(wrap);
  fields.set(key, el);
  return el;
}
function group(form, title) {
  const section = node('fieldset');
  section.append(node('legend', title));
  form.append(section);
  return section;
}
function refresh() {
  for (const section of dialog.querySelectorAll('fieldset')) section.disabled = busy || !!activeJob;
  for (const [key, el] of fields) el.disabled = !!activeJob || key === 'crf' && model.rate_control !== 'crf' || key === 'bitrate_mbps' && model.rate_control !== 'bitrate' || ['start_sec', 'end_sec'].includes(key) && model.range_mode !== 'range' || key.startsWith('audio_') && !model.audio;
  for (const o of fields.get('codec').options) o.disabled = model.container === 'mov' ? o.value === 'av1' : model.container === 'webm' ? o.value !== 'av1' : false;
  for (const o of fields.get('audio_codec').options) o.disabled = model.container === 'webm' ? o.value !== 'opus' : ['mp4', 'mov'].includes(model.container) ? o.value !== 'aac' : false;
  dialog.querySelector('#export-submit').disabled = busy || !!activeJob;
  dialog.querySelector('#export-cancel-job').hidden = !activeJob;
  dialog.querySelector('#export-summary').textContent = `${model.width} × ${model.height} · ${Number((model.fps_num / model.fps_den).toFixed(3))} fps · ${model.codec.toUpperCase()} / ${model.container.toUpperCase()} · SDR Rec.709`;
}
function build() {
  fields.clear();
  dialog.replaceChildren();
  const header = node('div', undefined, {
    class: 'export-header'
  });
  header.append(node('h2', 'Export video', {
    id: 'export-title'
  }), button('Close', () => dialog.close(), {
    'aria-label': 'Close export settings'
  }));
  const body = node('div', undefined, {
    class: 'export-body'
  });
  dialog.append(header, body);
  body.append(node('p', `Export revision ${revision}. Later edits remain available while this version renders.`, {
    class: 'muted small'
  }));
  const form = node('form', undefined, {
    id: 'export-form',
    class: 'export-grid'
  });
  body.append(form);
  const destination = group(form, 'Save locally');
  field(destination, 'filename', 'Filename');
  const folderRow = node('div', undefined, {
    class: 'export-inline'
  });
  destination.append(folderRow);
  field(folderRow, 'folder', 'Folder');
  folderRow.append(button('Use Desktop', () => {
    model.folder = defaults.settings.folder;
    fields.get('folder').value = model.folder;
  }));
  const video = group(form, 'Picture'),
    presets = node('select', undefined, {
      'aria-label': 'Export preset'
    });
  for (const p of defaults.presets) presets.append(node('option', p.name, {
    value: p.name
  }));
  presets.append(node('option', 'Custom', {
    value: 'Custom'
  }));
  presets.addEventListener('change', () => {
    const p = defaults.presets.find(p => p.name === presets.value);
    if (p) for (const k of ['width', 'height', 'fps_num', 'fps_den']) {
      model[k] = p[k];
      fields.get(k).value = model[k];
    }
    refresh();
  });
  const presetLabel = node('label', 'Preset');
  presetLabel.append(presets);
  video.append(presetLabel);
  field(video, 'width', 'Width', null, {
    min: 16,
    max: 7680,
    step: 2
  });
  field(video, 'height', 'Height', null, {
    min: 16,
    max: 7680,
    step: 2
  });
  const aspect = node('select', undefined, {
    'aria-label': 'Export aspect ratio'
  });
  for (const [value, text] of [['', 'Custom'], ['16:9', '16:9 landscape'], ['9:16', '9:16 portrait'], ['1:1', '1:1 square'], ['4:3', '4:3']]) aspect.append(node('option', text, {
    value
  }));
  aspect.addEventListener('change', () => {
    if (!aspect.value) return;
    const [w, h] = aspect.value.split(':').map(Number);
    model.height = Math.max(16, Math.min(7680, Math.round(model.width * h / w / 2) * 2));
    fields.get('height').value = model.height;
    presets.value = 'Custom';
    refresh();
  });
  const aspectLabel = node('label', 'Aspect ratio');
  aspectLabel.append(aspect);
  video.append(aspectLabel);
  field(video, 'fps_num', 'FPS numerator', null, {
    min: 1,
    max: 240000,
    step: 1
  });
  field(video, 'fps_den', 'FPS denominator', null, {
    min: 1,
    max: 10000,
    step: 1
  });
  video.append(node('p', 'For 23.976 or 29.97 fps, use 24000/1001 or 30000/1001.', {
    class: 'muted small'
  }));
  const encoding = group(form, 'Encoding');
  field(encoding, 'container', 'Container', ['mp4', 'mov', 'mkv', 'webm']);
  field(encoding, 'codec', 'Video codec', [['h264', 'H.264'], ['hevc', 'HEVC / H.265'], ['av1', 'AV1']]);
  field(encoding, 'encoder', 'Encoder', [['auto', 'Auto'], ['cpu', 'CPU'], ['gpu', 'GPU when available']]);
  field(encoding, 'quality', 'Quality', ['fast', 'standard', 'high', 'archival']);
  field(encoding, 'rate_control', 'Rate control', [['quality', 'Quality preset'], ['crf', 'Constant quality (CRF)'], ['bitrate', 'Bitrate']]);
  field(encoding, 'crf', 'CRF', null, {
    min: 0,
    max: 51,
    step: 1
  });
  field(encoding, 'bitrate_mbps', 'Video bitrate (Mbps)', null, {
    min: .1,
    max: 500,
    step: .1
  });
  field(encoding, 'speed', 'Encoding speed', [['fast', 'Fast'], ['balanced', 'Balanced'], ['slow', 'Slow']]);
  const range = group(form, 'Time range');
  field(range, 'range_mode', 'Export', [['full', 'Full project'], ['range', 'Selected range']]);
  field(range, 'start_sec', 'Start (seconds)', null, {
    min: 0,
    max: defaults.duration_sec,
    step: 'any'
  });
  field(range, 'end_sec', 'End (seconds)', null, {
    min: 0,
    max: defaults.duration_sec,
    step: 'any'
  });
  const audio = group(form, 'Audio');
  field(audio, 'audio', 'Include audio');
  field(audio, 'audio_codec', 'Audio codec', [['aac', 'AAC'], ['opus', 'Opus'], ['pcm_s16le', 'PCM 16-bit']]);
  field(audio, 'audio_bitrate_kbps', 'Audio bitrate (kbps)', null, {
    min: 32,
    max: 512,
    step: 1
  });
  field(audio, 'audio_sample_rate', 'Sample rate', [44100, 48000, 96000]);
  field(audio, 'audio_channels', 'Channels', [[1, 'Mono'], [2, 'Stereo']]);
  field(group(form, 'Captions'), 'captions', 'Captions', [['burn', 'Include visible captions'], ['none', 'Exclude captions']]);
  const actions = node('div', undefined, {
      class: 'export-actions'
    }),
    meta = node('div', undefined, {
      class: 'export-meta'
    }),
    buttons = node('div', undefined, {
      class: 'export-buttons'
    }),
    submit = node('button', 'Export video', {
      id: 'export-submit',
      type: 'submit',
      form: 'export-form',
      class: 'btn btn-primary'
    });
  meta.append(node('p', '', {
    id: 'export-summary',
    class: 'export-summary'
  }), node('p', '', {
    id: 'export-status',
    role: 'status',
    'aria-live': 'polite'
  }), node('div', undefined, {
    id: 'export-result'
  }));
  buttons.append(button('Cancel export', () => activeJob && request(`/render_jobs/${activeJob}/cancel`, {}), {
    id: 'export-cancel-job'
  }), submit);
  actions.append(meta, buttons);
  dialog.append(actions);
  form.addEventListener('submit', safe(async event => {
    event.preventDefault();
    if (busy || activeJob) return;
    if (!form.reportValidity()) return;
    const captured = project;
    busy = true;
    dialog.querySelector('#export-result').replaceChildren();
    refresh();
    status('Capturing source revision…');
    submit.disabled = true;
    try {
      const job = await request('/export', {
        expected_revision: revision,
        settings: model
      });
      activeJob = job.job_id;
      refresh();
      status('Rendering captured source…');
      await poll(job.job_id, captured, ++pollGeneration);
    } finally {
      activeJob = null;
      busy = false;
      refresh();
    }
  }));
  refresh();
}
async function poll(id, captured, generation) {
  for (;;) {
    await new Promise(resolve => setTimeout(resolve, 1500));
    if (generation !== pollGeneration) return;
    let job;
    try {
      job = await request(`/render_jobs/${id}`, undefined, captured);
    } catch (error) {
      status(`Connection interrupted. Retrying export status: ${error.message}`);
      continue;
    }
    if (job.status === 'succeeded') {
      const warnings = job.result?.warnings || [];
      dialog.querySelector('#export-result').replaceChildren(node('p', job.output_path, {
        class: 'export-path'
      }), ...warnings.map(text => node('p', text, {
        class: 'export-warning',
        role: 'status',
        style: 'color: var(--warn)'
      })), button('Play', () => request(`/exports/${id}/open/play`, {}, captured)), button('Open folder', () => request(`/exports/${id}/open/folder`, {}, captured)));
      status('Export verified and saved.');
      showToast(`Saved ${job.output_path}`, 'success');
      window.dispatchEvent(new CustomEvent('openedit:export-complete', {
        detail: {
          projectId: captured,
          job
        }
      }));
      return;
    }
    if (['failed', 'cancelled', 'orphaned'].includes(job.status)) throw new Error(job.error || `Export ${job.status}`);
    status(job.status === 'queued' ? 'Queued · source revision captured' : job.status === 'cancelling' ? 'Cancelling export…' : 'Rendering and verifying captured source…');
  }
}
export async function openExportDialog() {
  if (dialog?.open || loading) return;
  if (activeJob || busy) {
    dialog.showModal();
    return;
  }
  const captured = state.currentProjectId;
  if (!captured) throw new Error('Select a project first.');
  loading = true;
  let response;
  try { response = await request('/export/settings', undefined, captured); }
  finally { loading = false; }
  if (state.currentProjectId !== captured) return;
  project = captured;
  defaults = response;
  revision = defaults.graph_revision;
  model = {
    ...defaults.settings,
    end_sec: defaults.duration_sec
  };
  if (!dialog) {
    dialog = node('dialog', undefined, {
      id: 'export-dialog',
      'aria-labelledby': 'export-title'
    });
    document.body.append(dialog);
  }
  build();
  dialog.showModal();
}
