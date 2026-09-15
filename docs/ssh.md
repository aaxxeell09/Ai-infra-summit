# Windows SSH setup and verified status

Verified on September 15, 2026 at 18:14 UTC from the development Mac to the Latitude. These are executed checks, not just the Windows setup agent's report.

| Check | Result |
|---|---|
| TCP connection to Windows OpenSSH | Passed; server advertises OpenSSH for Windows 9.5 |
| Server identity | Ed25519 fingerprint matched the operator's setup photo and was pinned locally |
| Public-key authentication | Passed with the dedicated project key, in noninteractive mode |
| Remote command | `whoami` returned the expected Windows account |
| Server service | `sshd` running, automatic startup, port 22 listening |
| Authorized key | Dedicated public key found in the administrator authorized-keys file |
| Firewall | Domain, Private and Public profiles enabled; both inspected SSH allow rules limited to the Mac's current IPv4 address |
| Remote PowerShell | 5.1.26100.9168 |

The photo included an earlier check with an empty fingerprint and zero matching keys. The authenticated remote check above confirmed the final configuration. Actual usernames, device addresses, fingerprints and raw diagnostic output are kept in local notes rather than this public repository.

## Latest connection check

Rechecked on **September 15, 2026 at 20:22 UTC**. The dedicated key authenticated from the development Mac, remote PowerShell executed, and `sshd` was running. The existing `Qualcomm-ADB`, `Qualcomm-GenieX`, `Qualcomm-Hub` and `Qualcomm-Demo-Browser` scheduled tasks all reported Running.

The code checkout on the Latitude is under the signed-in account's `Documents/Ai-infra-summit` directory. Development uses SSH for commands and SCP for file transfer. The browser camera belongs to the signed-in Windows session; keep that session awake during the demo.

### Local alias and dashboard tunnel

Copy [ssh-config.example](../scripts/ssh-config.example) to a private SSH configuration file and replace its address and account placeholders with the kit's current values. Add the public key to Windows and pin the verified host key as described below. The example contains no credentials.

```sh
ssh -F ~/.ssh/config_qualcomm_latitude qualcomm-latitude whoami
ssh -F ~/.ssh/config_qualcomm_latitude -N -L 127.0.0.1:8081:127.0.0.1:8080 qualcomm-latitude
```

The second command keeps a tunnel open. The station console is then available on the development machine at `http://127.0.0.1:8081`. It forwards the Latitude's loopback-only hub without exposing a dashboard port to the venue Wi-Fi. The local port is bound only to loopback. Run the camera on the Latitude; the development console can display the image received by the hub.

To transfer a source file:

```sh
scp -F ~/.ssh/config_qualcomm_latitude path/to/file qualcomm-latitude:Documents/Ai-infra-summit/path/to/file
```

Changing the Wi-Fi network may change both machines' addresses. Check the Latitude address locally and update the private SSH config and Windows firewall source restriction before reconnecting. Repository files never contain the Windows password, SSH private key or device-specific host identity.

## Reproduce setup

1. On the development machine, create a dedicated Ed25519 key with `ssh-keygen`. Keep the private key on that machine; transfer only its `.pub` content.
2. On the Latitude, install Windows' built-in OpenSSH Server if missing, using an elevated PowerShell session. Start `sshd` and choose the desired service startup behavior.
3. Add the public key without replacing existing keys. Standard accounts use their profile's `.ssh/authorized_keys`; administrator accounts normally use `%ProgramData%/ssh/administrators_authorized_keys`. Apply the permissions required by Windows OpenSSH.
4. Keep Windows Firewall enabled and limit the SSH inbound rules to the development machine's address, including a broad rule created by the installer. If Wi-Fi changes the address, update the rule deliberately.
5. Read the server's public Ed25519 fingerprint locally on the Latitude and compare it on the development machine before trusting the host. Pin the matching host key. Do not disable host-key checking.
6. Test a remote command with the dedicated identity and `BatchMode=yes`. Verify the service, authorized-key presence and firewall settings over that connection.

For an existing local SSH alias, the verification command is:

```sh
ssh -o BatchMode=yes -o StrictHostKeyChecking=yes <latitude-alias> whoami
```

A successful SSH connection enables terminal commands and file transfer. It does not prove that camera capture, GenieX inference or an Arduino sketch works. Those have separate acceptance checks in [the execution plan](plan.md).

References: [Microsoft installation guide](https://learn.microsoft.com/en-us/windows-server/administration/openssh/openssh_install_firstuse), [Windows key management](https://learn.microsoft.com/en-us/windows-server/administration/openssh/openssh_keymanagement), [server configuration](https://learn.microsoft.com/en-us/windows-server/administration/openssh/openssh-server-configuration).
