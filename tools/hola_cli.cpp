// Tiny TGLF-in / TGLF-out wrapper around dialect::doHOLA.
//
// Usage: hola_cli --in <input.tglf> --out <output.tglf>
//
// Build via tools/build_hola_cli.sh (consults ADAPTAGRAMS_DIR for the
// libdialect / libavoid / libcola / libtopology / libvpsc source tree).
// _hola.py picks the resulting binary up via the HOLA_CLI env var or
// the `hola_cli` name on PATH.

#include <cstdlib>
#include <fstream>
#include <iostream>
#include <string>

#include "libdialect/commontypes.h"
#include "libdialect/graphs.h"
#include "libdialect/hola.h"
#include "libdialect/io.h"
#include "libdialect/opts.h"

namespace {

void usage(const char* prog) {
    std::cerr << "usage: " << prog << " --in <input.tglf> --out <output.tglf>\n";
}

}  // namespace

int main(int argc, char** argv) {
    std::string in_path, out_path;
    for (int i = 1; i < argc; ++i) {
        std::string a = argv[i];
        if (a == "--in" && i + 1 < argc) {
            in_path = argv[++i];
        } else if (a == "--out" && i + 1 < argc) {
            out_path = argv[++i];
        } else if (a == "-h" || a == "--help") {
            usage(argv[0]);
            return 0;
        } else {
            std::cerr << "unknown arg: " << a << "\n";
            usage(argv[0]);
            return 2;
        }
    }
    if (in_path.empty() || out_path.empty()) {
        usage(argv[0]);
        return 2;
    }

    try {
        dialect::Graph_SP graph = dialect::buildGraphFromTglfFile(in_path);
        dialect::HolaOpts opts;
        dialect::doHOLA(*graph, opts);
        std::ofstream out(out_path);
        if (!out) {
            std::cerr << "could not open output: " << out_path << "\n";
            return 1;
        }
        // useExternalIds=true so the IDs we wrote into the input TGLF
        // round-trip out to _hola.py's parser.
        out << graph->writeTglf(true);
        return 0;
    } catch (const std::exception& e) {
        std::cerr << "hola_cli: " << e.what() << "\n";
        return 1;
    } catch (...) {
        std::cerr << "hola_cli: unknown exception\n";
        return 1;
    }
}
