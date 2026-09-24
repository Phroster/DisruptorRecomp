# 🤝 Contributing

Thanks for helping make Disruptor Recompiled better! There are lots of ways to help,
and most of them don't need any programming.

## 🎮 Play and report

The most useful thing right now is people **playing the game** on their own PCs.

- **Found a problem?** [Open a bug report](https://github.com/Phroster/DisruptorRecomp/issues/new/choose).
  Tell us which level you were in, what you did and what happened. Please attach the logs:
  in the launcher click **Logs folder** and add `game-last.log` (and `build-last.log` if the
  build failed). Logs can contain your Windows user name; remove it if you like.
- **Everything worked?** That helps too. Tell us which levels you finished and on which PC,
  graphics card and controller.
- **Ideas** for improvements are welcome as [feature requests](https://github.com/Phroster/DisruptorRecomp/issues/new/choose).

## 🧑‍💻 Work on the code

The project translates the original PlayStation program into C with
[PSXRecomp](https://github.com/RetroPortingToolKit/psxrecomp) and adds its improvements
through patches and small mods. To build it yourself you need your own disc image;
[docs/BUILDING.md](docs/BUILDING.md) walks you through it.

A few ground rules keep the project clean and legal:

- **Never commit game data.** No disc images, extracted files, generated C code, captures or saves.
  They stay on your PC (the `.gitignore` already covers the usual places).
- **Don't edit generated code.** Fix the recompiler input (`game.toml`, `seeds/`), the framework
  patches in `patches/` or the mods in `src/` and `mods/`, then rebuild.
- **Keep the original game working.** New features should be switchable and keep the original
  controls, speed and 4:3 picture available.
- Explain in your pull request what changed and how you checked it.

## ⚖️ License

By contributing you agree that your work is shared under the project's
[PolyForm Noncommercial License 1.0.0](LICENSE).
