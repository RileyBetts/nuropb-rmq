/* Copyright © 2026, Riley Betts Ltd (rileybetts.ai)
 * Released under Apache 2.0 license as described in the file LICENSE.
 *
 * Optional OpenSSL AMQPS (tls-verify-full). Not linked by defaultTargets.
 */
#include <lean/lean.h>
#include <openssl/ssl.h>
#include <openssl/err.h>
#include <openssl/pem.h>
#include <openssl/x509.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>
#include <stdio.h>

static lean_obj_res io_error(const char *msg) {
  return lean_io_result_mk_error(lean_mk_io_user_error(lean_mk_string(msg)));
}

typedef struct {
  SSL_CTX *ctx;
  SSL *ssl;
  int fd;
} NuropbTls;

static void ensure_ssl(void) {
  static int once = 0;
  if (!once) {
    SSL_load_error_strings();
    OpenSSL_add_ssl_algorithms();
    once = 1;
  }
}

LEAN_EXPORT lean_obj_res nuropb_tls_connect(
    uint32_t fd,
    b_lean_obj_arg hostname,
    b_lean_obj_arg ca_pem,
    b_lean_obj_arg cert_pem,
    b_lean_obj_arg key_pem,
    lean_obj_arg w) {
  (void)w;
  ensure_ssl();
  const SSL_METHOD *method = TLS_client_method();
  SSL_CTX *ctx = SSL_CTX_new(method);
  if (!ctx) return io_error("SSL_CTX_new failed");
  SSL_CTX_set_verify(ctx, SSL_VERIFY_PEER, NULL);
  const char *ca = lean_string_cstr(ca_pem);
  if (ca[0] != '\0') {
    BIO *bio = BIO_new_mem_buf(ca, -1);
    X509 *cert = PEM_read_bio_X509(bio, NULL, 0, NULL);
    BIO_free(bio);
    if (!cert) {
      SSL_CTX_free(ctx);
      return io_error("failed to parse CA PEM");
    }
    X509_STORE *store = SSL_CTX_get_cert_store(ctx);
    X509_STORE_add_cert(store, cert);
    X509_free(cert);
  } else {
    SSL_CTX_set_default_verify_paths(ctx);
  }
  const char *cert = lean_string_cstr(cert_pem);
  const char *key = lean_string_cstr(key_pem);
  if (cert[0] != '\0' && key[0] != '\0') {
    BIO *cbio = BIO_new_mem_buf(cert, -1);
    X509 *xc = PEM_read_bio_X509(cbio, NULL, 0, NULL);
    BIO_free(cbio);
    BIO *kbio = BIO_new_mem_buf(key, -1);
    EVP_PKEY *pk = PEM_read_bio_PrivateKey(kbio, NULL, 0, NULL);
    BIO_free(kbio);
    if (!xc || !pk || SSL_CTX_use_certificate(ctx, xc) != 1 ||
        SSL_CTX_use_PrivateKey(ctx, pk) != 1) {
      if (xc) X509_free(xc);
      if (pk) EVP_PKEY_free(pk);
      SSL_CTX_free(ctx);
      return io_error("failed to load client cert/key");
    }
    X509_free(xc);
    EVP_PKEY_free(pk);
  }
  SSL *ssl = SSL_new(ctx);
  if (!ssl) {
    SSL_CTX_free(ctx);
    return io_error("SSL_new failed");
  }
  SSL_set_fd(ssl, (int)fd);
  const char *hn = lean_string_cstr(hostname);
  if (hn[0] != '\0') {
    SSL_set_tlsext_host_name(ssl, hn);
    SSL_set1_host(ssl, hn);
  }
  if (SSL_connect(ssl) != 1) {
    SSL_free(ssl);
    SSL_CTX_free(ctx);
    return io_error("SSL_connect failed (tls-verify-full)");
  }
  NuropbTls *sess = (NuropbTls *)malloc(sizeof(NuropbTls));
  if (!sess) {
    SSL_free(ssl);
    SSL_CTX_free(ctx);
    return io_error("oom");
  }
  sess->ctx = ctx;
  sess->ssl = ssl;
  sess->fd = (int)fd;
  return lean_io_result_mk_ok(lean_box_uint64((uint64_t)(uintptr_t)sess));
}

LEAN_EXPORT lean_obj_res nuropb_tls_send(uint64_t handle, b_lean_obj_arg buf, lean_obj_arg w) {
  (void)w;
  NuropbTls *sess = (NuropbTls *)(uintptr_t)handle;
  size_t n = lean_sarray_size(buf);
  uint8_t *data = lean_sarray_cptr(buf);
  size_t sent = 0;
  while (sent < n) {
    int r = SSL_write(sess->ssl, data + sent, (int)(n - sent));
    if (r <= 0) return io_error("SSL_write failed");
    sent += (size_t)r;
  }
  return lean_io_result_mk_ok(lean_box(0));
}

LEAN_EXPORT lean_obj_res nuropb_tls_pending(uint64_t handle, lean_obj_arg w) {
  (void)w;
  NuropbTls *sess = (NuropbTls *)(uintptr_t)handle;
  if (!sess || !sess->ssl) return lean_io_result_mk_ok(lean_box(0));
  int n = SSL_pending(sess->ssl);
  return lean_io_result_mk_ok(lean_box(n > 0 ? 1 : 0));
}

LEAN_EXPORT lean_obj_res nuropb_tls_recv(uint64_t handle, uint32_t max, lean_obj_arg w) {
  (void)w;
  NuropbTls *sess = (NuropbTls *)(uintptr_t)handle;
  if (max == 0) max = 4096;
  lean_object *arr = lean_alloc_sarray(1, 0, max);
  uint8_t *dst = lean_sarray_cptr(arr);
  int r = SSL_read(sess->ssl, dst, (int)max);
  if (r <= 0) {
    lean_dec(arr);
    return io_error("SSL_read failed");
  }
  lean_sarray_set_size(arr, (size_t)r);
  return lean_io_result_mk_ok(arr);
}

LEAN_EXPORT lean_obj_res nuropb_tls_close(uint64_t handle, lean_obj_arg w) {
  (void)w;
  NuropbTls *sess = (NuropbTls *)(uintptr_t)handle;
  if (sess) {
    SSL_shutdown(sess->ssl);
    SSL_free(sess->ssl);
    SSL_CTX_free(sess->ctx);
    free(sess);
  }
  return lean_io_result_mk_ok(lean_box(0));
}
