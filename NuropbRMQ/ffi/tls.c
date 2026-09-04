/* Copyright © 2026, Riley Betts Ltd (rileybetts.ai)
 * Released under Apache 2.0 license as described in the file LICENSE.
 *
 * Optional OpenSSL AMQPS (tls-verify-full). Memory BIO + SSL_ERROR_WANT_*;
 * no SSL_set_fd and no blocking SSL_connect/read/write. UV owns the TCP
 * socket. Not linked by defaultTargets.
 */
#include <lean/lean.h>
#include <openssl/ssl.h>
#include <openssl/err.h>
#include <openssl/bio.h>
#include <openssl/pem.h>
#include <openssl/pkcs12.h>
#include <openssl/provider.h>
#include <openssl/x509.h>
#include <openssl/evp.h>
#include <openssl/ecdsa.h>
#include <openssl/bn.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>
#include <stdio.h>
#include <pthread.h>

#define TLS_DONE 0
#define TLS_WANT_READ 1
#define TLS_WANT_WRITE 2

static lean_obj_res io_error(const char *msg) {
  return lean_io_result_mk_error(lean_mk_io_user_error(lean_mk_string(msg)));
}

static lean_obj_res io_error_ssl(const char *msg) {
  unsigned long err = ERR_get_error();
  char buf[256];
  if (err == 0) return io_error(msg);
  ERR_error_string_n(err, buf, sizeof(buf));
  char out[384];
  snprintf(out, sizeof(out), "%s: %s", msg, buf);
  return io_error(out);
}

typedef struct {
  SSL_CTX *ctx;
  SSL *ssl;
  BIO *rbio;
  BIO *wbio;
  int last_want;
  int dead;
  pthread_mutex_t mu;
} NuropbTls;

static pthread_once_t g_ssl_once = PTHREAD_ONCE_INIT;

static void ensure_ssl_once(void) {
  /* Do not register OPENSSL_cleanup as atexit: process exit races the UV
     loop thread (`lean_uv_tcp_recv` / task_manager::resolve) and SIGSEGVs. */
  OPENSSL_init_ssl(OPENSSL_INIT_NO_ATEXIT, NULL);
  OPENSSL_init_crypto(OPENSSL_INIT_NO_ATEXIT | OPENSSL_INIT_LOAD_CONFIG, NULL);
  (void)OSSL_PROVIDER_load(NULL, "default");
  SSL_load_error_strings();
  OpenSSL_add_ssl_algorithms();
}

static void ensure_ssl(void) {
  pthread_once(&g_ssl_once, ensure_ssl_once);
}

static NuropbTls *sess_lock(uint64_t handle) {
  NuropbTls *sess = (NuropbTls *)(uintptr_t)handle;
  if (!sess) return NULL;
  pthread_mutex_lock(&sess->mu);
  if (sess->dead || !sess->ssl) {
    pthread_mutex_unlock(&sess->mu);
    return NULL;
  }
  return sess;
}

static void sess_unlock(NuropbTls *sess) {
  pthread_mutex_unlock(&sess->mu);
}

static uint64_t pack_want(uint32_t st, uint32_t n) {
  return ((uint64_t)st << 32) | (uint64_t)n;
}

static lean_object *empty_bytes(void) {
  return lean_alloc_sarray(1, 0, 0);
}

static int ssl_want(SSL *ssl, int r) {
  int err = SSL_get_error(ssl, r);
  if (err == SSL_ERROR_WANT_READ) return TLS_WANT_READ;
  if (err == SSL_ERROR_WANT_WRITE) return TLS_WANT_WRITE;
  return -1;
}

static lean_obj_res finish_new(SSL_CTX *ctx, const char *hn) {
  SSL *ssl = SSL_new(ctx);
  if (!ssl) {
    SSL_CTX_free(ctx);
    return io_error("SSL_new failed");
  }
  BIO *rbio = BIO_new(BIO_s_mem());
  BIO *wbio = BIO_new(BIO_s_mem());
  if (!rbio || !wbio) {
    if (rbio) BIO_free(rbio);
    if (wbio) BIO_free(wbio);
    SSL_free(ssl);
    SSL_CTX_free(ctx);
    return io_error("BIO_new failed");
  }
  BIO_set_mem_eof_return(rbio, -1);
  BIO_set_mem_eof_return(wbio, -1);
  SSL_set_bio(ssl, rbio, wbio);
  SSL_clear_mode(ssl, SSL_MODE_AUTO_RETRY);
  SSL_set_mode(ssl, SSL_MODE_ENABLE_PARTIAL_WRITE | SSL_MODE_ACCEPT_MOVING_WRITE_BUFFER);
  SSL_set_connect_state(ssl);
  if (hn[0] != '\0') {
    SSL_set_tlsext_host_name(ssl, hn);
    SSL_set1_host(ssl, hn);
  }
  NuropbTls *sess = (NuropbTls *)malloc(sizeof(NuropbTls));
  if (!sess) {
    SSL_free(ssl);
    SSL_CTX_free(ctx);
    return io_error("oom");
  }
  sess->ctx = ctx;
  sess->ssl = ssl;
  sess->rbio = rbio;
  sess->wbio = wbio;
  sess->last_want = TLS_DONE;
  sess->dead = 0;
  if (pthread_mutex_init(&sess->mu, NULL) != 0) {
    SSL_free(ssl);
    SSL_CTX_free(ctx);
    free(sess);
    return io_error("tls mutex init failed");
  }
  return lean_io_result_mk_ok(lean_box_uint64((uint64_t)(uintptr_t)sess));
}

static SSL_CTX *new_verify_ctx(void) {
  const SSL_METHOD *method = TLS_client_method();
  SSL_CTX *ctx = SSL_CTX_new(method);
  if (!ctx) return NULL;
  SSL_CTX_set_verify(ctx, SSL_VERIFY_PEER, NULL);
  return ctx;
}

LEAN_EXPORT lean_obj_res nuropb_tls_new(
    b_lean_obj_arg hostname,
    b_lean_obj_arg ca_pem,
    b_lean_obj_arg cert_pem,
    b_lean_obj_arg key_pem,
    lean_obj_arg w) {
  (void)w;
  ensure_ssl();
  SSL_CTX *ctx = new_verify_ctx();
  if (!ctx) return io_error("SSL_CTX_new failed");
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
  return finish_new(ctx, lean_string_cstr(hostname));
}

LEAN_EXPORT lean_obj_res nuropb_tls_new_pkcs12(
    b_lean_obj_arg hostname,
    b_lean_obj_arg ca_pem,
    b_lean_obj_arg p12_path,
    b_lean_obj_arg password,
    lean_obj_arg w) {
  (void)w;
  ensure_ssl();
  SSL_CTX *ctx = new_verify_ctx();
  if (!ctx) return io_error("SSL_CTX_new failed");
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
  FILE *fp = fopen(lean_string_cstr(p12_path), "rb");
  if (!fp) {
    SSL_CTX_free(ctx);
    return io_error("failed to open PKCS#12 file");
  }
  PKCS12 *p12 = d2i_PKCS12_fp(fp, NULL);
  fclose(fp);
  if (!p12) {
    SSL_CTX_free(ctx);
    return io_error("failed to parse PKCS#12");
  }
  EVP_PKEY *pk = NULL;
  X509 *xc = NULL;
  STACK_OF(X509) *ca_stack = NULL;
  size_t plen = lean_string_size(password);
  char passbuf[256];
  if (plen >= sizeof(passbuf)) {
    PKCS12_free(p12);
    SSL_CTX_free(ctx);
    return io_error("PKCS#12 password too long");
  }
  memcpy(passbuf, lean_string_cstr(password), plen);
  passbuf[plen] = '\0';
  if (PKCS12_parse(p12, plen == 0 ? NULL : passbuf, &pk, &xc, &ca_stack) != 1 ||
      !xc || !pk) {
    PKCS12_free(p12);
    if (pk) EVP_PKEY_free(pk);
    if (xc) X509_free(xc);
    if (ca_stack) sk_X509_pop_free(ca_stack, X509_free);
    SSL_CTX_free(ctx);
    return io_error_ssl("failed to load PKCS#12 client cert/key");
  }
  PKCS12_free(p12);
  if (SSL_CTX_use_certificate(ctx, xc) != 1 || SSL_CTX_use_PrivateKey(ctx, pk) != 1) {
    EVP_PKEY_free(pk);
    X509_free(xc);
    if (ca_stack) sk_X509_pop_free(ca_stack, X509_free);
    SSL_CTX_free(ctx);
    return io_error("failed to install PKCS#12 client cert/key");
  }
  X509_free(xc);
  EVP_PKEY_free(pk);
  if (ca_stack) {
    X509_STORE *store = SSL_CTX_get_cert_store(ctx);
    for (int i = 0; i < sk_X509_num(ca_stack); i++) {
      X509 *extra = sk_X509_value(ca_stack, i);
      if (extra) X509_STORE_add_cert(store, extra);
    }
    sk_X509_pop_free(ca_stack, X509_free);
  }
  return finish_new(ctx, lean_string_cstr(hostname));
}

LEAN_EXPORT lean_obj_res nuropb_tls_handshake_step(uint64_t handle, lean_obj_arg w) {
  (void)w;
  NuropbTls *sess = sess_lock(handle);
  if (!sess) return io_error("tls handle closed");
  int r = SSL_do_handshake(sess->ssl);
  if (r == 1) {
    int vok = SSL_get_verify_result(sess->ssl) == X509_V_OK;
    sess_unlock(sess);
    if (!vok) return io_error("TLS peer verify failed (tls-verify-full)");
    return lean_io_result_mk_ok(lean_unsigned_to_nat(TLS_DONE));
  }
  int want = ssl_want(sess->ssl, r);
  sess_unlock(sess);
  if (want < 0) return io_error_ssl("SSL_do_handshake failed (tls-verify-full)");
  return lean_io_result_mk_ok(lean_unsigned_to_nat((unsigned)want));
}

LEAN_EXPORT lean_obj_res nuropb_tls_feed(uint64_t handle, b_lean_obj_arg buf, lean_obj_arg w) {
  (void)w;
  NuropbTls *sess = sess_lock(handle);
  if (!sess || !sess->rbio) {
    if (sess) sess_unlock(sess);
    return io_error("tls handle closed");
  }
  size_t n = lean_sarray_size(buf);
  if (n == 0) {
    sess_unlock(sess);
    return lean_io_result_mk_ok(lean_box(0));
  }
  uint8_t *data = lean_sarray_cptr(buf);
  int r = BIO_write(sess->rbio, data, (int)n);
  sess_unlock(sess);
  if (r <= 0 || (size_t)r != n) return io_error("BIO_write (tls feed) failed");
  return lean_io_result_mk_ok(lean_box(0));
}

LEAN_EXPORT lean_obj_res nuropb_tls_drain(uint64_t handle, lean_obj_arg w) {
  (void)w;
  NuropbTls *sess = sess_lock(handle);
  if (!sess || !sess->wbio) {
    if (sess) sess_unlock(sess);
    return lean_io_result_mk_ok(empty_bytes());
  }
  unsigned char tmp[16384];
  size_t cap = 16384;
  size_t used = 0;
  uint8_t *acc = (uint8_t *)malloc(cap);
  if (!acc) {
    sess_unlock(sess);
    return io_error("oom");
  }
  for (;;) {
    int r = BIO_read(sess->wbio, tmp, (int)sizeof(tmp));
    if (r <= 0) break;
    if (used + (size_t)r > cap) {
      cap = (used + (size_t)r) * 2;
      uint8_t *nacc = (uint8_t *)realloc(acc, cap);
      if (!nacc) {
        free(acc);
        sess_unlock(sess);
        return io_error("oom");
      }
      acc = nacc;
    }
    memcpy(acc + used, tmp, (size_t)r);
    used += (size_t)r;
  }
  sess_unlock(sess);
  if (used == 0) {
    free(acc);
    return lean_io_result_mk_ok(empty_bytes());
  }
  lean_object *arr = lean_alloc_sarray(1, 0, used);
  memcpy(lean_sarray_cptr(arr), acc, used);
  lean_sarray_set_size(arr, used);
  free(acc);
  return lean_io_result_mk_ok(arr);
}

LEAN_EXPORT lean_obj_res nuropb_tls_write(uint64_t handle, b_lean_obj_arg buf, lean_obj_arg w) {
  (void)w;
  NuropbTls *sess = sess_lock(handle);
  if (!sess) return io_error("tls handle closed");
  size_t n = lean_sarray_size(buf);
  if (n == 0) {
    sess->last_want = TLS_DONE;
    sess_unlock(sess);
    return lean_io_result_mk_ok(lean_box_uint64(pack_want(TLS_DONE, 0)));
  }
  uint8_t *data = lean_sarray_cptr(buf);
  int r = SSL_write(sess->ssl, data, (int)n);
  if (r > 0) {
    sess->last_want = TLS_DONE;
    sess_unlock(sess);
    return lean_io_result_mk_ok(lean_box_uint64(pack_want(TLS_DONE, (uint32_t)r)));
  }
  int want = ssl_want(sess->ssl, r);
  if (want < 0) {
    sess_unlock(sess);
    return io_error_ssl("SSL_write failed");
  }
  sess->last_want = want;
  sess_unlock(sess);
  return lean_io_result_mk_ok(lean_box_uint64(pack_want((uint32_t)want, 0)));
}

LEAN_EXPORT lean_obj_res nuropb_tls_read(uint64_t handle, uint32_t max, lean_obj_arg w) {
  (void)w;
  NuropbTls *sess = sess_lock(handle);
  if (!sess) return io_error("tls handle closed");
  if (max == 0) max = 4096;
  lean_object *arr = lean_alloc_sarray(1, 0, max);
  uint8_t *dst = lean_sarray_cptr(arr);
  int r = SSL_read(sess->ssl, dst, (int)max);
  if (r > 0) {
    sess->last_want = TLS_DONE;
    lean_sarray_set_size(arr, (size_t)r);
    sess_unlock(sess);
    return lean_io_result_mk_ok(arr);
  }
  lean_dec(arr);
  if (r == 0) {
    int err = SSL_get_error(sess->ssl, r);
    if (err == SSL_ERROR_ZERO_RETURN) {
      sess->last_want = TLS_DONE;
      sess_unlock(sess);
      return lean_io_result_mk_ok(empty_bytes());
    }
  }
  int want = ssl_want(sess->ssl, r);
  if (want < 0) {
    sess_unlock(sess);
    return io_error_ssl("SSL_read failed");
  }
  sess->last_want = want;
  sess_unlock(sess);
  return lean_io_result_mk_ok(empty_bytes());
}

LEAN_EXPORT lean_obj_res nuropb_tls_pending(uint64_t handle, lean_obj_arg w) {
  (void)w;
  NuropbTls *sess = sess_lock(handle);
  if (!sess) return lean_io_result_mk_ok(lean_box(0));
  int n = SSL_pending(sess->ssl);
  sess_unlock(sess);
  return lean_io_result_mk_ok(lean_box(n > 0 ? 1 : 0));
}

LEAN_EXPORT lean_obj_res nuropb_tls_last_want(uint64_t handle, lean_obj_arg w) {
  (void)w;
  NuropbTls *sess = (NuropbTls *)(uintptr_t)handle;
  if (!sess) return lean_io_result_mk_ok(lean_unsigned_to_nat(TLS_DONE));
  pthread_mutex_lock(&sess->mu);
  int want = sess->dead ? TLS_DONE : sess->last_want;
  pthread_mutex_unlock(&sess->mu);
  return lean_io_result_mk_ok(lean_unsigned_to_nat((unsigned)want));
}

LEAN_EXPORT lean_obj_res nuropb_tls_shutdown_step(uint64_t handle, lean_obj_arg w) {
  (void)w;
  NuropbTls *sess = sess_lock(handle);
  if (!sess) return lean_io_result_mk_ok(lean_unsigned_to_nat(TLS_DONE));
  int r = SSL_shutdown(sess->ssl);
  if (r >= 0) {
    sess_unlock(sess);
    return lean_io_result_mk_ok(lean_unsigned_to_nat(TLS_DONE));
  }
  int want = ssl_want(sess->ssl, r);
  sess_unlock(sess);
  if (want < 0) return lean_io_result_mk_ok(lean_unsigned_to_nat(TLS_DONE));
  return lean_io_result_mk_ok(lean_unsigned_to_nat((uint32_t)want));
}

LEAN_EXPORT lean_obj_res nuropb_tls_close(uint64_t handle, lean_obj_arg w) {
  (void)w;
  NuropbTls *sess = (NuropbTls *)(uintptr_t)handle;
  if (!sess) return lean_io_result_mk_ok(lean_box(0));
  pthread_mutex_lock(&sess->mu);
  if (!sess->dead) {
    if (sess->ssl) SSL_free(sess->ssl);
    if (sess->ctx) SSL_CTX_free(sess->ctx);
    sess->ssl = NULL;
    sess->ctx = NULL;
    sess->rbio = NULL;
    sess->wbio = NULL;
    sess->dead = 1;
  }
  pthread_mutex_unlock(&sess->mu);
  /* Keep the session allocation so a late FFI call cannot UAF the mutex. */
  return lean_io_result_mk_ok(lean_box(0));
}

static char *dup_lean_string(b_lean_obj_arg s) {
  size_t n = lean_string_size(s);
  char *p = (char *)malloc(n == 0 ? 1 : n);
  if (!p) return NULL;
  if (n == 0) {
    p[0] = '\0';
    return p;
  }
  memcpy(p, lean_string_cstr(s), n);
  return p;
}

static int ecdsa_p1363_to_der(const unsigned char *raw, size_t rawlen,
                              unsigned char **out, size_t *outlen) {
  if (rawlen == 0 || (rawlen % 2) != 0) return 0;
  size_t half = rawlen / 2;
  ECDSA_SIG *esig = ECDSA_SIG_new();
  if (!esig) return 0;
  BIGNUM *r = BN_bin2bn(raw, (int)half, NULL);
  BIGNUM *s = BN_bin2bn(raw + half, (int)half, NULL);
  if (!r || !s || ECDSA_SIG_set0(esig, r, s) != 1) {
    BN_free(r);
    BN_free(s);
    ECDSA_SIG_free(esig);
    return 0;
  }
  int len = i2d_ECDSA_SIG(esig, NULL);
  if (len <= 0) {
    ECDSA_SIG_free(esig);
    return 0;
  }
  *out = (unsigned char *)malloc((size_t)len);
  if (!*out) {
    ECDSA_SIG_free(esig);
    return 0;
  }
  unsigned char *p = *out;
  i2d_ECDSA_SIG(esig, &p);
  *outlen = (size_t)len;
  ECDSA_SIG_free(esig);
  return 1;
}

/* RS256 / ES256 JWS verify. Returns IO Bool (false = fail-closed). */
LEAN_EXPORT lean_obj_res nuropb_jwt_verify_asymmetric(
    b_lean_obj_arg alg,
    b_lean_obj_arg pem_pub,
    b_lean_obj_arg signing,
    b_lean_obj_arg sig,
    lean_obj_arg w) {
  (void)w;
  ensure_ssl();
  char *alg_s = dup_lean_string(alg);
  char *pem = dup_lean_string(pem_pub);
  char *msg = dup_lean_string(signing);
  if (!alg_s || !pem || !msg) {
    free(alg_s);
    free(pem);
    free(msg);
    return io_error("oom");
  }
  size_t msg_len = strlen(msg);
  size_t sig_len = lean_sarray_size(sig);
  const unsigned char *sig_raw = lean_sarray_cptr(sig);
  int ok = 0;
  if (pem[0] == '\0' || msg_len == 0 || sig_len == 0) {
    goto done;
  }
  BIO *bio = BIO_new_mem_buf(pem, -1);
  if (!bio) goto done;
  EVP_PKEY *pkey = PEM_read_bio_PUBKEY(bio, NULL, NULL, NULL);
  BIO_free(bio);
  if (!pkey) goto done;
  const unsigned char *use_sig = sig_raw;
  unsigned char *der = NULL;
  size_t use_len = sig_len;
  if (strcmp(alg_s, "ES256") == 0) {
    if (!ecdsa_p1363_to_der(sig_raw, sig_len, &der, &use_len)) {
      EVP_PKEY_free(pkey);
      goto done;
    }
    use_sig = der;
  } else if (strcmp(alg_s, "RS256") != 0) {
    EVP_PKEY_free(pkey);
    goto done;
  }
  EVP_MD_CTX *ctx = EVP_MD_CTX_new();
  if (ctx &&
      EVP_DigestVerifyInit(ctx, NULL, EVP_sha256(), NULL, pkey) == 1 &&
      EVP_DigestVerify(ctx, use_sig, use_len, (const unsigned char *)msg, msg_len) == 1) {
    ok = 1;
  }
  if (ctx) EVP_MD_CTX_free(ctx);
  EVP_PKEY_free(pkey);
  free(der);
done:
  free(alg_s);
  free(pem);
  free(msg);
  return lean_io_result_mk_ok(lean_box(ok ? 1 : 0));
}
