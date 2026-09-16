# Venue-to-home remote access

Verified 2026-09-15 on the current network: both machines joined the same private Tailscale network; a fresh key-authenticated OpenSSH connection to the Latitude's Tailscale address succeeded. TCP ports 22 and 3389 were reachable through that address. This is not yet a different-network test or a successful graphical desktop login.

The Windows Tailscale service is automatic and running with unattended mode (`ForceDaemon=true`). Existing OpenSSH remains in use. Windows Remote Desktop is enabled with Network Level Authentication; the added inbound RDP rule is scoped to this Mac's Tailscale address. No public router port forwarding was configured.

The private Mac SSH alias is `qualcomm-remote`. Its identity file, host address and known-host mapping remain outside Git. It retains strict host-key verification against the previously verified Latitude key. The original LAN alias is preserved.

```sh
ssh qualcomm-remote
# Optional local web access; restart this command after a connection drop.
ssh -N -L 18083:127.0.0.1:8083 qualcomm-remote
```

The tunnel only transports the service; service health is a separate check. Tailscale reconnects independently of an SSH process. An interrupted SSH tunnel must be restarted or supervised explicitly.

Keep the Latitude plugged in with its lid open. The authorized keep-awake helper has a 12-hour lifetime and releases its request on exit; it does not permanently change the power plan or override lid-close behavior. Renew through `Start-ScheduledTask -TaskName 'Qualcomm-KeepAwake'` when the previous run has ended. A running job must be restarted to renew its deadline. Do not sign out while interactive scheduled workloads are needed.

Before leaving, switch the Mac to a different network, open a fresh SSH connection, verify the tuner independently, and test a desktop login if needed. The Windows App client installation and offsite reconnection remain pending. Credentials, account identifiers, host addresses, login URLs and private evidence must never be committed here.
