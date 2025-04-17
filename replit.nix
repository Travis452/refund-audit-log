{pkgs}: {
  deps = [
    pkgs.tesseract
    pkgs.libGLU
    pkgs.libGL
    pkgs.postgresql
    pkgs.openssl
  ];
}
