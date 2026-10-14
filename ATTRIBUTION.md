# Attribution and maintenance

This is Labyricorn's maintained fork of
[mir-aidj/all-in-one](https://github.com/mir-aidj/all-in-one), originally created by
Taejun Kim. The original repository history, MIT license, copyright notice and
research citation are retained. The initial installed upstream revision was
`18e78903c0365147a2c5d4e5e57ebf88cb7d800e`.

Labyricorn additions include the unified song CLI, MCP interface, lyric
transcription/alignment adapters, combined song maps, persistent/offline jobs,
tests, Windows constraints and Demucs compatibility fixes. Newly added project
code is provided under the repository's MIT license. Keeping the `allin1` package
name preserves the existing API; repository branding can evolve separately.

Preserve the upstream citation when using the analyzer in research:

```bibtex
@inproceedings{taejun2023allinone,
  title={All-In-One Metrical And Functional Structure Analysis With Neighborhood Attentions on Demixed Audio},
  author={Kim, Taejun and Nam, Juhan},
  booktitle={IEEE Workshop on Applications of Signal Processing to Audio and Acoustics (WASPAA)},
  year={2023}
}
```

`patches/natten-0.14.6-windows.patch` modifies SHI-Labs NATTEN v0.14.6
(`3b54c76185904f3cb59a49fff7bc044e4513d106`). Its original MIT copyright and
permission notice are retained in `patches/NATTEN-LICENSE`. NATTEN source/builds
are installed independently, not vendored as a second repository here.

Other dependencies and downloaded pretrained models retain their own licenses
and notices. The repository's MIT license applies to its code; it does not
relicense third-party dependencies, model weights, user audio, or evaluation data.
No user songs, lyrics, model binaries, environments, job outputs, or external
research datasets are included in the fork's source additions.
