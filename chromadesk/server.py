"""Expose the chromatography desk and the shared image-preparation workspace."""

from io import BytesIO
import os
from pathlib import Path

from flask import Blueprint, jsonify, render_template, request, send_file, url_for

from image_lab import create_app as preparation_app
from image_lab.validation import Conflict, Invalid, choice, integer, number, object_value

from . import bands, demo, density, locator, outputs, peaks, photo
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
        result = dict(revision=current["revision"], **density.read(image, current["settings"], x, y))
        wants_peak = any(request.args.get(name) is not None for name in (
            "band", "band_index", "index", "i", "first_y", "last_y",
            "start_y", "end_y", "peak_y", "band_y", "peak", "peak_review", "review")
        )
        if wants_peak:
            selected, index = band_for_review(current, image)
            review = selected.get("peak_review") or peaks.review_band(
                image, current["settings"], selected)
            check = peaks.peak_at_column(image, current["settings"], x, review=review)
            result["band_index"] = index
            result["peak_check"] = check
            result["column_peak"] = check
            result["peak"] = check
            result["peak_review"] = review
            if check.get("peak_y") is not None:
                result["peak_probe"] = density.read(
                    image, current["settings"], x, check["peak_y"])
        return jsonify(result)

    @desk.get("/cards/<key>/locate")
    def locate(key):
        current, image = current_image(key)
        x = integer(request.args.get("x"), "回查列", 0, current["size"][0] - 1)
        fraction = number(request.args.get("rf"), "目标迁移率", 0, 1)
        settings = current["settings"]
        x, y = locator.locate(settings, x, fraction)
        return jsonify(revision=current["revision"], **density.read(image, settings, x, y))

    def optional_int(args, name, label, minimum, maximum):
        raw = args.get(name)
        if raw is None or raw == "":
            return None
        return integer(raw, label, minimum, maximum)

    def band_for_review(current, image, band_index=None):
        report = bands.profile(image, current["settings"])
        recognized = report["bands"]
        if not recognized:
            raise Invalid("当前设置没有认出的色带，无法重核峰位")

        if band_index is None:
            band_index = optional_int(request.args, "band", "色带编号", 0, len(recognized) - 1)
        for name in ("band_index", "index", "i"):
            if band_index is None:
                band_index = optional_int(request.args, name, "色带编号", 0, len(recognized) - 1)

        if band_index is not None:
            if band_index >= len(recognized):
                raise Invalid("没有这条色带")
            return recognized[band_index], band_index

        first_y = optional_int(request.args, "first_y", "色带首行", 0, current["size"][1] - 1)
        last_y = optional_int(request.args, "last_y", "色带末行", 0, current["size"][1] - 1)
        if first_y is None:
            first_y = optional_int(request.args, "start_y", "色带首行", 0, current["size"][1] - 1)
        if last_y is None:
            last_y = optional_int(request.args, "end_y", "色带末行", 0, current["size"][1] - 1)
        if first_y is not None and last_y is not None:
            for index, item in enumerate(recognized):
                if item["first_y"] == first_y and item["last_y"] == last_y:
                    return item, index
            review = peaks.review_band(image, current["settings"],
                                       {"first_y": first_y, "last_y": last_y})
            return review, None

        peak_y = optional_int(request.args, "peak_y", "色带参考峰行", 0, current["size"][1] - 1)
        if peak_y is None:
            peak_y = optional_int(request.args, "band_y", "色带参考峰行", 0, current["size"][1] - 1)
        if peak_y is not None:
            for index, item in enumerate(recognized):
                if item["first_y"] <= peak_y <= item["last_y"]:
                    return item, index

        return recognized[0], 0

    def peak_response(key, band_index=None, x_value=None):
        current, image = current_image(key)
        width, height = current["size"]
        x_raw = x_value if x_value is not None else request.args.get("x")
        if x_raw is None:
            x_raw = request.args.get("column", request.args.get("column_x"))
        x = integer(x_raw, "原片列", 0, width - 1)
        selected, index = band_for_review(current, image, band_index)
        review = selected.get("peak_review") or peaks.review_band(image, current["settings"], selected)
        result = peaks.peak_at_column(image, current["settings"], x, review=review)
        result["revision"] = current["revision"]
        result["band_index"] = index
        result["band"] = {
            "first_y": review["first_y"], "last_y": review["last_y"],
            "candidate_ys": review["candidate_ys"],
            "measured_peak": review["measured_peak"],
            "lane_columns": review["lane_columns"],
            "common_columns": review["common_columns"],
        }
        y = optional_int(request.args, "y", "原片行", 0, height - 1)
        if y is not None:
            result["probe"] = density.read(image, current["settings"], x, y)
        if result.get("peak_y") is not None:
            result["peak_probe"] = density.read(image, current["settings"], x, result["peak_y"])
        return jsonify(result)

    @desk.get("/cards/<key>/peak-reviews")
    def peak_reviews_route(key):
        current, image = current_image(key)
        report = bands.profile(image, current["settings"])
        return jsonify(revision=current["revision"], peaks=report["peak_reviews"],
                       peak_reviews=report["peak_reviews"])

    @desk.get("/cards/<key>/peak")
    def peak(key):
        return peak_response(key)

    @desk.get("/cards/<key>/peaks")
    def peaks_alias(key):
        return peak_response(key)

    @desk.get("/cards/<key>/recheck-peak")
    def recheck_peak_route(key):
        return peak_response(key)

    @desk.get("/cards/<key>/bands/<int:band_index>/peak")
    def band_peak(key, band_index):
        return peak_response(key, band_index)

    @desk.get("/cards/<key>/peak/<int:x_value>")
    def peak_at_path_column(key, x_value):
        return peak_response(key, x_value=x_value)

    @desk.get("/cards/<key>/bands/<int:band_index>/peak/<int:x_value>")
    def band_peak_at_path_column(key, band_index, x_value):
        return peak_response(key, band_index, x_value)

    @desk.get("/cards/<key>/recheck")
    def recheck_route(key):
        return peak_response(key)

    @desk.get("/cards/<key>/review")
    def review_route(key):
        return peak_response(key)

    @desk.get("/cards/<key>/peak-review")
    def peak_review_alias_route(key):
        return peak_response(key)

    @desk.get("/cards/<key>/peak_review")
    def peak_review_underscore_route(key):
        return peak_response(key)

    @desk.get("/cards/<key>/bands/<int:band_index>/recheck")
    def band_recheck_route(key, band_index):
        return peak_response(key, band_index)

    @desk.get("/cards/<key>/bands/<int:band_index>/probe")
    def band_probe_route(key, band_index):
        return peak_response(key, band_index)

    @desk.get("/peak")
    def peak_by_query_card():
        key = request.args.get("card") or request.args.get("key") or request.args.get("id")
        if not key:
            raise Invalid("缺少层析卡编号")
        return peak_response(key)

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
