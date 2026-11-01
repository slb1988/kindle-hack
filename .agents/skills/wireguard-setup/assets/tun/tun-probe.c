#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <linux/if_tun.h>
#include <net/if.h>
#include <stdio.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/stat.h>
#include <sys/sysmacros.h>
#include <unistd.h>

/* Create one nonpersistent, unaddressed interface and close it immediately.
 * No packets, routes, DNS, existing links, or persistent interfaces are changed.
 * This exercises the TUN ioctls used by the shipped wireguard-go release.
 */
static int fail(const char *stage, int fd) {
    int saved = errno;
    if (fd >= 0) close(fd);
    fprintf(stderr, "TUN probe failed at %s: %s\n", stage, strerror(saved));
    return 1;
}

int main(int argc, char **argv) {
    if (argc != 2 || strcmp(argv[1], "--verify") != 0) {
        puts("usage: tun-probe --verify\nCreates and closes a temporary TUN interface; no IP or route changes.");
        return argc == 2 && strcmp(argv[1], "--help") == 0 ? 0 : 2;
    }
    alarm(8);
    struct stat st;
    if (stat("/dev/net/tun", &st) < 0) return fail("stat", -1);
    if (!S_ISCHR(st.st_mode) || major(st.st_rdev) != 10 || minor(st.st_rdev) != 200) {
        fputs("TUN probe: refusing an unexpected device node\n", stderr);
        return 1;
    }
    int fd = open("/dev/net/tun", O_RDWR | O_CLOEXEC);
    if (fd < 0) return fail("open", -1);
    unsigned int features = 0;
    if (ioctl(fd, TUNGETFEATURES, &features) < 0) return fail("TUNGETFEATURES", fd);
    unsigned int required = IFF_TUN | IFF_NO_PI | IFF_VNET_HDR;
    if ((features & required) != required) {
        fprintf(stderr, "TUN probe: missing required features (got 0x%x, need 0x%x)\n", features, required);
        close(fd);
        return 1;
    }
    struct ifreq ifr;
    memset(&ifr, 0, sizeof(ifr));
    memcpy(ifr.ifr_name, "kwgtst%d", sizeof("kwgtst%d"));
    ifr.ifr_flags = (short)(required | IFF_TUN_EXCL);
    if (ioctl(fd, TUNSETIFF, &ifr) < 0) return fail("TUNSETIFF", fd);
    char name[IFNAMSIZ];
    memcpy(name, ifr.ifr_name, sizeof(name));
    name[IFNAMSIZ - 1] = '\0';
    if (ioctl(fd, TUNGETIFF, &ifr) < 0) return fail("TUNGETIFF", fd);
    unsigned int offloads = TUN_F_CSUM | TUN_F_TSO4 | TUN_F_TSO6;
    if (ioctl(fd, TUNSETOFFLOAD, offloads) < 0) return fail("TUNSETOFFLOAD", fd);
    int header_size = 0;
    if (ioctl(fd, TUNGETVNETHDRSZ, &header_size) < 0) return fail("TUNGETVNETHDRSZ", fd);
    if (header_size != 10) {
        fprintf(stderr, "TUN probe: unexpected virtio header size %d\n", header_size);
        close(fd);
        return 1;
    }
    if (close(fd) < 0) return fail("close", -1);
    if (if_nametoindex(name) != 0) {
        fprintf(stderr, "TUN probe: temporary interface %s still exists after close\n", name);
        return 1;
    }
    alarm(0);
    printf("{\"tunFeatures\":%u,\"createdInterface\":\"%s\",\"wireguardTcpOffloads\":true,\"virtioHeaderBytes\":%d,\"interfaceRemoved\":true,\"addressesAssigned\":false,\"routesChanged\":false}\n", features, name, header_size);
    return 0;
}
