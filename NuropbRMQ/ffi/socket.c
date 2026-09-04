/* Copyright © 2026, Riley Betts Ltd (rileybetts.ai)
 * Released under Apache 2.0 license as described in the file LICENSE.
 *
 * POSIX TCP + /dev/urandom for NuropbRMQ. No OpenSSL.
 */
#include <lean/lean.h>
#include <sys/types.h>
#include <sys/socket.h>
#include <netdb.h>
#include <netinet/in.h>
#include <arpa/inet.h>
#include <unistd.h>
#include <fcntl.h>
#include <poll.h>
#include <errno.h>
#include <string.h>
#include <stdio.h>

static lean_obj_res io_error(const char *msg) {
  return lean_io_result_mk_error(lean_mk_io_user_error(lean_mk_string(msg)));
}

LEAN_EXPORT lean_obj_res nuropb_tcp_connect(b_lean_obj_arg host, uint16_t port, lean_obj_arg w) {
  (void)w;
  const char *h = lean_string_cstr(host);
  char portstr[16];
  snprintf(portstr, sizeof(portstr), "%u", (unsigned)port);
  struct addrinfo hints;
  memset(&hints, 0, sizeof(hints));
  hints.ai_family = AF_UNSPEC;
  hints.ai_socktype = SOCK_STREAM;
  struct addrinfo *res = NULL;
  if (getaddrinfo(h, portstr, &hints, &res) != 0 || res == NULL) {
    return io_error("getaddrinfo failed");
  }
  int fd = -1;
  for (struct addrinfo *p = res; p != NULL; p = p->ai_next) {
    fd = socket(p->ai_family, p->ai_socktype, p->ai_protocol);
    if (fd < 0) continue;
    if (connect(fd, p->ai_addr, p->ai_addrlen) == 0) break;
    close(fd);
    fd = -1;
  }
  freeaddrinfo(res);
  if (fd < 0) return io_error("connect failed");
  return lean_io_result_mk_ok(lean_box_uint32((uint32_t)fd));
}

LEAN_EXPORT lean_obj_res nuropb_tcp_send(uint32_t fd, b_lean_obj_arg buf, lean_obj_arg w) {
  (void)w;
  size_t n = lean_sarray_size(buf);
  uint8_t *data = lean_sarray_cptr(buf);
  size_t sent = 0;
  while (sent < n) {
    ssize_t r = send((int)fd, data + sent, n - sent, 0);
    if (r < 0) {
      if (errno == EINTR) continue;
      return io_error("send failed");
    }
    sent += (size_t)r;
  }
  return lean_io_result_mk_ok(lean_box(0));
}

LEAN_EXPORT lean_obj_res nuropb_tcp_recv(uint32_t fd, uint32_t max, lean_obj_arg w) {
  (void)w;
  if (max == 0) max = 4096;
  lean_object *arr = lean_alloc_sarray(1, 0, max);
  uint8_t *dst = lean_sarray_cptr(arr);
  ssize_t r;
  do {
    r = recv((int)fd, dst, max, 0);
  } while (r < 0 && errno == EINTR);
  if (r < 0) {
    lean_dec(arr);
    return io_error("recv failed");
  }
  if (r == 0) {
    lean_dec(arr);
    return io_error("connection closed");
  }
  lean_sarray_set_size(arr, (size_t)r);
  return lean_io_result_mk_ok(arr);
}

LEAN_EXPORT lean_obj_res nuropb_tcp_poll(uint32_t fd, uint32_t timeout_ms, lean_obj_arg w) {
  (void)w;
  struct pollfd pfd;
  pfd.fd = (int)fd;
  pfd.events = POLLIN;
  pfd.revents = 0;
  int r;
  do {
    r = poll(&pfd, 1, (int)timeout_ms);
  } while (r < 0 && errno == EINTR);
  if (r < 0) return io_error("poll failed");
  return lean_io_result_mk_ok(lean_box(r > 0 && (pfd.revents & POLLIN) ? 1 : 0));
}

LEAN_EXPORT lean_obj_res nuropb_tcp_close(uint32_t fd, lean_obj_arg w) {
  (void)w;
  close((int)fd);
  return lean_io_result_mk_ok(lean_box(0));
}

LEAN_EXPORT lean_obj_res nuropb_random_bytes(uint32_t n, lean_obj_arg w) {
  (void)w;
  lean_object *arr = lean_alloc_sarray(1, n, n);
  uint8_t *dst = lean_sarray_cptr(arr);
  int rfd = open("/dev/urandom", O_RDONLY);
  if (rfd < 0) {
    lean_dec(arr);
    return io_error("open /dev/urandom failed");
  }
  size_t got = 0;
  while (got < n) {
    ssize_t r = read(rfd, dst + got, n - got);
    if (r <= 0) {
      close(rfd);
      lean_dec(arr);
      return io_error("read /dev/urandom failed");
    }
    got += (size_t)r;
  }
  close(rfd);
  return lean_io_result_mk_ok(arr);
}
