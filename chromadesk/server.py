"""Expose the chromatography desk and the shared image-preparation workspace."""

from io import BytesIO
import os
from pathlib import Path

from flask import Blueprint, jsonify, render_template, request, send_file, url_for

from image_lab import create_app as preparation_app
from image_lab.validation import Conflict, Invalid, choice, integer, number, object_value

from . import bands, demo, density, locator, outputs, photo
from .cards import Cards


def download(data, mime, name=None):
    return send_file(BytesIO(data), mimetype=mime, max_age=0,
                     as_attachment=name is not None, download_name=name)


def create_app(data=None):
    directory = Path(data or os.environ.get("CHROMADESK_DATA", ".chromadesk-data")).resolve()
    app = preparation_app(directory / "prepare")
    cards = Cards(directory / "strips")
    desk = Blueprint("chroma", __name__, url_prefix="/chroma")

    @app.get("/")
    def home():
        return render_template("chromadesk.html")

    @desk.get("/health")
    def health():
        return jsonify(status="ok", app="chromadesk")

    @desk.get("/preview.png")
    def preview():
        png, _ = demo.practice("two-inks")
        return download(png, "image/png")

    @desk.route("/cards", methods=["GET", "POST"])
    def collection():
        if request.method == "GET":
            return jsonify(cards=cards.list())
        request.max_content_length = 15 * 1024 * 1024
        upload = request.files.get("source")
        if not upload or not upload.filename:
            raise Invalid("请选择原片")
        name = Path(upload.filename.replace(chr(92), "/")).name[:120]
        size, png = photo.decode(upload.stream.read(photo.MAX_IMAGE_BYTES + 1))
        return jsonify(cards.create(request.form.get("name"), name, size, png)), 201

    @desk.post("/practice")
    def practice():
        payload = object_value(request.get_json(silent=True), "练习选项")
        kind = choice(payload.get("sample"), "练习", demo.EXERCISES)
        png, settings = demo.practice(kind)
        title = "弯湿线双墨样" if kind == "two-inks" else "平湿线单墨样"
        return jsonify(cards.create(title, f"{kind}.png", demo.SIZE, png, settings, synthetic=True)), 201

    @desk.route("/cards/<key>", methods=["GET", "PATCH"])
    def card(key):
        if request.method == "PATCH":
            return jsonify(cards.save(key, object_value(request.get_json(silent=True), "采用设置")))
        return jsonify(cards.read(key))

    @desk.get("/cards/<key>/source.png")
    def original(key):
        return download(cards.image(key), "image/png")

    def current_image(key):
        current = cards.read(key)
        revision = request.args.get("rev")
        if revision is not None and integer(revision, "采用版本", 1) != current["revision"]:
            raise Conflict("卡片版本已更新，请重新打开")
        return current, photo.pixels(BytesIO(cards.image(key)))

    @desk.get("/cards/<key>/report")
    def report(key):
        current, image = current_image(key)
        return jsonify(revision=current["revision"], **bands.profile(image, current["settings"]))

    @desk.get("/cards/<key>/probe")
    def probe(key):
        current, image = current_image(key)
        x = integer(request.args.get("x"), "原片列", 0, current["size"][0] - 1)
        y = integer(request.args.get("y"), "原片行", 0, current["size"][1] - 1)
        return jsonify(revision=current["revision"], **density.read(image, current["settings"], x, y))

    @desk.get("/cards/<key>/locate")
    def locate(key):
        current, image = current_image(key)
        x = integer(request.args.get("x"), "回查列", 0, current["size"][0] - 1)
        fraction = number(request.args.get("rf"), "目标迁移率", 0, 1)
        settings = current["settings"]
        x, y = locator.locate(settings, x, fraction)
        return jsonify(revision=current["revision"], **density.read(image, settings, x, y))

    @desk.get("/cards/<key>/density.png")
    def density_image(key):
        current, image = current_image(key)
        return download(outputs.density_preview(image, current["settings"]), "image/png")

    @desk.get("/cards/<key>/strip.png")
    def strip(key):
        current, image = current_image(key)
        return download(outputs.strip_png(image, current["settings"]), "image/png", "chromadesk-strip.png")

    @desk.get("/cards/<key>/trace.csv")
    def trace(key):
        current, image = current_image(key)
        return download(outputs.trace_csv(bands.profile(image, current["settings"])), "text/csv", "chromadesk-trace.csv")

    @desk.post("/cards/<key>/prepare")
    def prepare(key):
        current, array = current_image(key)
        source = array.astype("float32") / 255
        services = app.extensions
        asset = services["assets"].put(source, current["source_name"])
        project = services["store"].create(f"{current['name']} · 原片准备")
        services["frames"].add(project["id"], project["revision"], [asset["id"]])
        return jsonify(url=url_for("index", project=project["id"])), 201

    app.register_blueprint(desk)
    return app
