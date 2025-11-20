#!/usr/bin/env python3
"""Generate evaluation datasets for retrieval and NLU.
- retrieval_eval.csv: query,relevant_ids (semicolon-separated ProposalLog IDs)
- intents_eval.csv: text,intent

This script will try to use existing ProposalLog rows. If not enough, it will synthesize proposals and insert them into DB for realistic IDs.
"""
from pathlib import Path
import random
import csv
import json

# Set up DB access using existing state_store
from backend.memory import state_store
from backend.memory.state_store import ProposalLog, SessionLocal, create_catalog_entry

OUT_RETR = Path('tests/data_examples/retrieval_eval.csv')
OUT_INTENTS = Path('tests/data_examples/intents_eval.csv')

random.seed(42)

def ensure_min_proposals(min_count=100):
    with SessionLocal() as db:
        count = db.query(ProposalLog).count()
        if count >= min_count:
            return
        # synthesize proposals
        for i in range(min_count - count):
            req = f"Proyecto de ejemplo sobre desarrollo de servicio {i} con requisitos de API y datos" \
                  f" que incluye integración con ML y despliegue en la nube."
            proposal = {
                'methodology': random.choice(['Scrum', 'Kanban', 'Scrumban']),
                'budget': {'total': 10000 + i*100},
                'team': [{'role': 'backend', 'count': 1}, {'role': 'frontend', 'count': 1}],
                'phases': ['analisis','desarrollo','qa']
            }
            row = ProposalLog(session_id=f'synth-{i}', requirements=req, proposal_json=proposal)
            db.add(row)
        db.commit()


def collect_proposal_texts(limit=500):
    with SessionLocal() as db:
        rows = db.query(ProposalLog).order_by(ProposalLog.created_at.desc()).limit(limit).all()
        return [{'id': r.id, 'text': (r.requirements or '').strip()} for r in rows]


def generate_retrieval_eval(proposals, n_queries=50):
    # choose queries by sampling proposal texts slightly perturbed
    rows = []
    for i in range(n_queries):
        base = random.choice(proposals)
        q = base['text']
        # perturb a bit
        q = q.replace('desarrollo', random.choice(['diseño','implementación','despliegue']))
        q = q[:200]
        # pick 3-5 relevant ids: include the base id plus some neighbors
        relevant = {base['id']}
        # sample some other ids with similar words (randomly)
        others = random.sample(proposals, min(10, len(proposals)))
        for o in others[:random.randint(2,4)]:
            relevant.add(o['id'])
        rows.append({'query': q, 'relevant_ids': ';'.join(str(x) for x in list(relevant))})
    OUT_RETR.parent.mkdir(parents=True, exist_ok=True)
    with OUT_RETR.open('w', encoding='utf-8', newline='') as fh:
        writer = csv.DictWriter(fh, fieldnames=['query','relevant_ids'])
        writer.writeheader()
        for r in rows:
            writer.writerow(r)
    print(f'Wrote retrieval eval with {len(rows)} queries to {OUT_RETR}')
    return rows


def generate_intents_eval(classes, per_class=60):
    # classes: list of intent labels
    rows = []
    templates = {
        'greet': ['Hola', 'Buenos días', 'Hola, ¿qué tal?', 'Hey', 'Buenas'],
        'goodbye': ['Adiós', 'Hasta luego', 'Nos vemos', 'Chao', 'Hasta pronto'],
        'thanks': ['Gracias', 'Muchas gracias', 'Gracias por la ayuda', 'Te lo agradezco'],
        'help': ['¿Qué puedes hacer?', 'Necesito ayuda', '¿Qué funcionalidades tienes?', 'Explícame tus capacidades'],
        'ask_budget': ['Necesito una estimación de coste', '¿Cuánto costaría?', 'Dame una estimación del presupuesto'],
        'ask_methodology': ['¿Qué metodología recomiendas?', '¿Usas Scrum o Kanban?', 'Recomienda una metodología'],
        'ask_team': ['Qué perfiles necesito?', '¿Cuántos desarrolladores?', 'Necesito roles para el proyecto'],
        'ask_risks': ['¿Qué riesgos ves?', 'Identifica riesgos del proyecto', 'Riesgos asociados a la entrega'],
        'ask_why_budget': ['Por qué ese presupuesto?', 'Justifica el coste', 'Explica el presupuesto'],
        'ask_why_methodology': ['Por qué esa metodología?', 'Justifica la metodología propuesta'],
        'ask_why_team': ['Por qué necesitas ese equipo?', 'Justifica la elección de perfiles'],
        'ask_why_role_count': ['Por qué necesitas 2 PMs?', 'Explica el número de roles propuesto']
    }

    noise = ['por favor','si es posible','en mi organización','con microservicios','con alto rendimiento']

    for intent in classes:
        for i in range(per_class):
            t = random.choice(templates.get(intent, ['Pregunta sobre el sistema']))
            # add variation
            if random.random() < 0.5:
                t = t + ' ' + random.choice(noise)
            if random.random() < 0.1:
                t = t + ' ' + str(random.randint(1,100))
            rows.append({'text': t, 'intent': intent})
    random.shuffle(rows)
    OUT_INTENTS.parent.mkdir(parents=True, exist_ok=True)
    with OUT_INTENTS.open('w', encoding='utf-8', newline='') as fh:
        writer = csv.DictWriter(fh, fieldnames=['text','intent'])
        writer.writeheader()
        for r in rows:
            writer.writerow(r)
    print(f'Wrote intents eval with {len(rows)} samples to {OUT_INTENTS}')
    return rows


def main():
    ensure_min_proposals(120)
    proposals = collect_proposal_texts(500)
    if len(proposals) < 50:
        print('Warning: not enough proposals found; created synthetic ones.')
    retr_rows = generate_retrieval_eval(proposals, n_queries=50)
    # intents classes discover from backend.nlu.intents
    from backend.nlu.intents import INTENT_LABELS
    intents_rows = generate_intents_eval(INTENT_LABELS, per_class=60)

if __name__ == '__main__':
    main()
