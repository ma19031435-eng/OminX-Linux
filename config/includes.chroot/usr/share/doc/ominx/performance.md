# OminX memory and game performance

## Memory compression without app suspension

OminX enables a zstd-compressed zram swap device. Under memory pressure the Linux kernel can compress less-active memory pages into RAM, then restore them when an app needs them. It does **not** freeze, close, hibernate, or intentionally pause whole applications. The zram device is capped at half of system memory or 4 GiB, whichever is smaller, and is preferred over slower disk swap.

This is page-level memory compression, not compression of installed app files. It uses some CPU time and still depends on available RAM; a workload that exceeds RAM plus zram can feel slower, and normal out-of-memory handling can still terminate a process if the machine is exhausted. On hardware without zstd support, the kernel may reject this configuration, so check `journalctl -b` and `/sys/block/zram0/comp_algorithm` after boot.

## Game Mode

Feral GameMode is installed. It requests available performance-oriented settings only while a game is launched through it; it does not apply a permanent high-power profile when no game is running.

For a Steam game, open **Library → game Properties → General → Launch Options** and enter:

```text
/usr/games/gamemoderun %command%
```

For Lutris, enable its **Feral GameMode** option for the game. You can test the daemon with `gamemoded -t` and inspect its status with `gamemoded -s` while a game is running.

No generic setting can promise a 50% latency reduction. Input latency, frame pacing, and network ping depend on the game, drivers, GPU/CPU, display, thermals, and network. GameMode can reduce avoidable scheduling or power-policy overhead on supported hardware, but it cannot change internet routing or guarantee a particular result. Compare the same scene and workload before and after; keep the configuration that measures better on your machine.
