# Open Edit Operator Setup

## Render sandbox cgroup

The render sandbox (`open-edit-render-sandbox`) applies `MemoryMax=4G` and
`CPUQuota=300%` to a cgroup v2 group. The cgroup must exist before the
sandbox is invoked, or the limits silently fail (now an error since I3
in v1.0).

### One-time setup per boot

```bash
sudo /home/ah64/apps/mlt-pipeline/bin/setup_render_cgroup.sh
```

The script is idempotent. It can be installed as a systemd unit:

```ini
# /etc/systemd/system/open-edit-render-cgroup.service
[Service]
Type=oneshot
ExecStart=/home/ah64/apps/mlt-pipeline/bin/setup_render_cgroup.sh
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable open-edit-render-cgroup.service
```

### Verify

```bash
cat /sys/fs/cgroup/open_edit_render/memory.max  # should show 4294967296 after a render
cat /sys/fs/cgroup/open_edit_render/cpu.max     # should show "300000 100000"
```

### Cleanup

```bash
sudo rmdir /sys/fs/cgroup/open_edit_render  # only when no renders are running
```

## cgroup v2 requirement

cgroup v2 must be mounted. On modern Linux (kernel 5.x+), this is the
default. On older systems or some distros, you may need:

```bash
# /etc/default/grub
GRUB_CMDLINE_LINUX="systemd.unified_cgroup_hierarchy=1"
```

Then `sudo update-grub && sudo reboot`.
