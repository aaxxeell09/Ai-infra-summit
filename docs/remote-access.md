# Venue-to-home remote access

Verified 2026-09-15: both machines joined the same private Tailscale network; a fresh key-authenticated OpenSSH connection to the Latitude's Tailscale address succeeded. TCP ports 22 and 3389 were reachable through that address. A subsequent fresh SSH process with multiplexing disabled succeeded after the Mac moved to a different network; the Latitude remained on the venue network. Tailscale reported a direct external endpoint. This verifies offsite SSH, not a successful graphical desktop login.

The Windows Tailscale service is automatic and running with unattended mode (`ForceDaemon=true`). Existing OpenSSH remains in use. Windows Remote Desktop is enabled with Network Level Authentication; the added inbound RDP rule is scoped to this Mac's Tailscale address. No public router port forwarding was configured.

The private Mac SSH alias is `qualcomm-remote`. Its identity file, host address and known-host mapping remain outside Git. It retains strict host-key verification against the previously verified Latitude key. The original LAN alias is preserved.

```sh
ssh qualcomm-remote
# Optional manual tunnel if the installed supervisor is not running:
ssh -N -L 127.0.0.1:18083:127.0.0.1:8083 qualcomm-remote
```

The tunnel only transports the service; service health is a separate check. Tailscale reconnects independently of an SSH process. The Mac now has a private per-user LaunchAgent supervising the loopback-only port 18083 tunnel. A termination/restart test verified automatic process recovery and subsequent service access. The tunnel can be healthy while the service is intentionally stopped for isolated measurements.

Keep the Latitude plugged in with its lid open. The authorized keep-awake helper has a 12-hour lifetime and releases its request on exit; it does not permanently change the power plan or override lid-close behavior. Renew through `Start-ScheduledTask -TaskName 'Qualcomm-KeepAwake'` when the previous run has ended. A running job must be restarted to renew its deadline. Do not sign out while interactive scheduled workloads are needed.

Before leaving, switch the Mac to a different network, open a fresh SSH connection, verify the tuner independently, and test a desktop login if needed. The notarized Microsoft Windows App 11.4.1 is installed in the Mac user Applications folder with a saved Tailscale PC entry. Its displayed self-signed certificate fingerprint matched the certificate obtained over strict-key SSH. RDP reached authentication but rejected the supplied credential; the Windows account is Microsoft-backed, so its account password may differ from the local sign-in PIN. No password was stored in the client. Desktop login remains pending; offsite SSH is verified. Credentials, account identifiers, host addresses, login URLs and private evidence must never be committed here.
