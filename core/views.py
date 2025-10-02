from django.contrib import messages
from django.http import HttpResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_GET, require_POST
from django.db import transaction
import json

from .models import Survey, ResponseSet, Answer, Question, Option, AccessToken


def survey_form(request, survey_id):
    survey = get_object_or_404(Survey, pk=survey_id, is_active=True)
    return render(request, "surveys/survey_form.html", {"survey": survey})


@require_GET
def ident_partial(request, survey_id):
    survey = get_object_or_404(Survey, pk=survey_id, is_active=True)
    return render(request, "surveys/_ident_step.html", {"survey": survey})


@require_POST
def check_ident(request, survey_id):
    survey = get_object_or_404(Survey, pk=survey_id, is_active=True)
    identificacion = request.POST.get("identificacion", "").strip()
    token = request.POST.get("token", "").strip()

    if not identificacion:
        messages.error(request, "Debes ingresar la identificación.")
        return HttpResponseBadRequest("Identificación requerida")

    # Duplicados por encuesta
    exists = ResponseSet.objects.filter(survey=survey, identificacion=identificacion).exists()
    if exists:
        messages.error(request, "Ya existe una respuesta con esta identificación para esta encuesta.")
        return HttpResponse("", status=409)

    # Token, si la encuesta lo exige
    ctx = {
        "survey": survey,
        "identificacion": identificacion,
        "full_name": request.POST.get("full_name", ""),
        "phone": request.POST.get("phone", ""),
        "email": request.POST.get("email", ""),
        "token": token or None,
    }

    if survey.require_token:
        if not token:
            messages.error(request, "Se requiere un token válido para responder esta encuesta.")
            return HttpResponseBadRequest("Token requerido")
        try:
            t = AccessToken.objects.get(survey=survey, token=token)
        except AccessToken.DoesNotExist:
            messages.error(request, "El token no es válido.")
            return HttpResponseBadRequest("Token inválido")
        if not t.is_valid():
            messages.error(request, "El token ya fue usado o está vencido.")
            return HttpResponseBadRequest("Token no vigente")
        if t.expected_identificacion and t.expected_identificacion != identificacion:
            messages.error(request, "La identificación no coincide con el token asignado.")
            return HttpResponseBadRequest("Token no corresponde")

    # Render del cuestionario completo como siguiente paso
    return render(request, "surveys/_section_block.html", ctx)


@require_POST
@transaction.atomic
def submit_response(request, survey_id):
    from django.template.loader import render_to_string
    survey = get_object_or_404(Survey, pk=survey_id, is_active=True)

    identificacion = request.POST.get("identificacion", "").strip()
    token = request.POST.get("token") or None
    full_name = request.POST.get("full_name", "")
    phone = request.POST.get("phone", "")
    email = request.POST.get("email", "")

    if not identificacion:
        # ← devolvemos 200 con alerta para que no salga error en consola
        messages.error(request, "Identificación requerida.")
        html = render_to_string("surveys/_alerts.html", request=request)
        resp = HttpResponse(html, status=200)
        resp["HX-Retarget"] = "#alerts"
        resp["HX-Reswap"] = "innerHTML"
        return resp

    # Duplicados por encuesta
    if ResponseSet.objects.filter(survey=survey, identificacion=identificacion).exists():
        messages.error(request, "Ya existe respuesta para esta identificación.")
        html = render_to_string("surveys/_alerts.html", request=request)
        resp = HttpResponse(html, status=200)
        resp["HX-Retarget"] = "#alerts"
        resp["HX-Reswap"] = "innerHTML"
        return resp

    # Token si aplica
    token_obj = None
    if survey.require_token:
        if not token:
            messages.error(request, "Se requiere token.")
            html = render_to_string("surveys/_alerts.html", request=request)
            resp = HttpResponse(html, status=200); resp["HX-Retarget"]="#alerts"; resp["HX-Reswap"]="innerHTML"
            return resp
        try:
            token_obj = AccessToken.objects.select_for_update().get(survey=survey, token=token)
        except AccessToken.DoesNotExist:
            messages.error(request, "Token inválido.")
            html = render_to_string("surveys/_alerts.html", request=request)
            resp = HttpResponse(html, status=200); resp["HX-Retarget"]="#alerts"; resp["HX-Reswap"]="innerHTML"
            return resp
        if not token_obj.is_valid():
            messages.error(request, "Token usado o vencido.")
            html = render_to_string("surveys/_alerts.html", request=request)
            resp = HttpResponse(html, status=200); resp["HX-Retarget"]="#alerts"; resp["HX-Reswap"]="innerHTML"
            return resp
        if token_obj.expected_identificacion and token_obj.expected_identificacion != identificacion:
            messages.error(request, "La identificación no coincide con el token.")
            html = render_to_string("surveys/_alerts.html", request=request)
            resp = HttpResponse(html, status=200); resp["HX-Retarget"]="#alerts"; resp["HX-Reswap"]="innerHTML"
            return resp

    # ---------- VALIDACIÓN DE PREGUNTAS (sin crear nada aún) ----------
    missing_q = None
    parsed_answers = []  # almacenamos temporalmente para crear luego

    for q in Question.objects.filter(section__survey=survey).select_related("section").prefetch_related("options"):
        opt_key = f"q_{q.id}__opts"
        text_key = f"q_{q.id}__text"
        int_key  = f"q_{q.id}__int"
        dec_key  = f"q_{q.id}__dec"
        bool_key = f"q_{q.id}__bool"
        date_key = f"q_{q.id}__date"

        option_ids = request.POST.getlist(opt_key)
        text_val   = request.POST.get(text_key)
        int_val    = request.POST.get(int_key)
        dec_val    = request.POST.get(dec_key)
        bool_val   = request.POST.get(bool_key)
        date_val   = request.POST.get(date_key)

        has_any = any([
            option_ids,
            text_val,
            int_val not in (None, ""),
            dec_val not in (None, ""),
            bool_val in ("true", "false"),
            date_val,
        ])

        if not has_any and q.required and missing_q is None:
            missing_q = q
            break

        parsed_answers.append((q, option_ids, text_val, int_val, dec_val, bool_val, date_val))

    if missing_q is not None:
        messages.error(request, f"La pregunta '{missing_q.code}' es obligatoria.")
        html = render_to_string("surveys/_alerts.html", request=request)
        # 200 para que htmx no registre error; se dispara evento para resaltar
        resp = HttpResponse(html, status=200)
        resp["HX-Retarget"] = "#alerts"
        resp["HX-Reswap"]   = "innerHTML"
        resp["HX-Trigger"]  = json.dumps({"validation-error": {"qid": missing_q.id}})
        return resp

    # ---------- AHORA SÍ: crear ResponseSet y Answers ----------
    rs = ResponseSet.objects.create(
        survey=survey,
        identificacion=identificacion,
        full_name=full_name,
        phone=phone,
        email=email,
        access_token=token_obj,
    )

    for q, option_ids, text_val, int_val, dec_val, bool_val, date_val in parsed_answers:
        # si no hay valor, saltar
        if not (option_ids or text_val or int_val not in (None, "") or dec_val not in (None, "") or bool_val in ("true","false") or date_val):
            continue

        ans = Answer.objects.create(response=rs, question=q)
        if q.qtype in ("single", "likert"):
            if option_ids:
                opts = Option.objects.filter(pk__in=option_ids, question=q)
                ans.options.set(opts[:1])  # forzamos opción única por seguridad
        elif q.qtype == "multi":
            if option_ids:
                opts = Option.objects.filter(pk__in=option_ids, question=q)
                if q.max_choices and opts.count() > q.max_choices:
                    transaction.set_rollback(True)
                    messages.error(request, f"'{q.code}' admite máximo {q.max_choices} selecciones.")
                    html = render_to_string("surveys/_alerts.html", request=request)
                    resp = HttpResponse(html, status=200)
                    resp["HX-Retarget"]="#alerts"; resp["HX-Reswap"]="innerHTML"
                    resp["HX-Trigger"] = json.dumps({"validation-error": {"qid": q.id}})
                    return resp
                ans.options.set(opts)
        elif q.qtype == "text":
            ans.text_answer = text_val or ""
            ans.save(update_fields=["text_answer"])
        elif q.qtype == "int":
            try: ans.integer_answer = int(int_val)
            except (TypeError, ValueError): ans.integer_answer = None
            ans.save(update_fields=["integer_answer"])
        elif q.qtype == "dec":
            from decimal import Decimal
            try: ans.decimal_answer = Decimal(dec_val)
            except Exception: ans.decimal_answer = None
            ans.save(update_fields=["decimal_answer"])
        elif q.qtype == "bool":
            ans.bool_answer = True if bool_val == "true" else False if bool_val == "false" else None
            ans.save(update_fields=["bool_answer"])
        elif q.qtype == "date":
            ans.date_answer = date_val or None
            ans.save(update_fields=["date_answer"])

    if token_obj:
        token_obj.used = True
        token_obj.save(update_fields=["used"])

    rs.refresh_scores(save=True)

    html = f"""
    <section class='space-y-4 text-center'>
      <h2 class='text-xl font-semibold'>¡Gracias por tu respuesta!</h2>
      <div class='mx-auto max-w-md rounded-xl border border-gray-200 bg-white p-4 shadow-sm'>
        <p class='text-sm text-gray-700'>ID de respuesta: <strong>{rs.id}</strong></p>
        <p class='mt-2'>Puntaje Zarit: <strong>{rs.zarit_score}</strong></p>
        <p class=''>Categoría: <strong class='capitalize'>{rs.zarit_category}</strong></p>
      </div>
      <a href='{request.build_absolute_uri(request.path.replace("/submit/","/"))}' class='text-gray-900 bg-white border border-gray-300 hover:bg-gray-100 focus:ring-4 focus:ring-gray-200 font-medium rounded-lg text-sm px-5 py-2.5'>Nueva respuesta</a>
    </section>
    """
    return HttpResponse(html)
