ARG BUILD_FROM
FROM ${BUILD_FROM}

# lsof: de bot gebruikt `lsof -ti :PORT` om achtergebleven webviewer-processen op
# te ruimen bij een herstart. Alpine's ingebouwde busybox-lsof snapt -t/-i niet en
# dumpt in plaats daarvan alle open file-handles van het systeem, wat de bot als
# ongeldige PID's ziet ("Invalid PID format, skipping") - het echte package uit
# Alpine's repo lost dit op, zonder dat we de bot-broncode hoeven aan te passen.
RUN apk add --no-cache python3 py3-pip git lsof

WORKDIR /opt/meshcore-bot

# Pin een vaste release i.p.v. main, zodat een update van de bot niet ongemerkt
# je add-on breekt. Werk deze tag bij wanneer je bewust wilt upgraden.
RUN git clone --depth 1 --branch v1.1.0 https://github.com/agessaman/meshcore-bot.git . \
    && pip3 install --no-cache-dir --break-system-packages -r requirements.txt


# Build-time patches on the upstream source, all in one step. local_patches/ORDER lists them in the order they run,
# each with what it fixes and why; apply_all.py stops the build on the first patch whose anchor text is not found
# exactly once (upstream changed - update that patch before upgrading).
COPY local_patches/ /tmp/local_patches/
RUN python3 /tmp/local_patches/apply_all.py && rm -rf /tmp/local_patches

# The add-on's own code, one step per folder (each file explains itself in its docstring):
# - local_shared/*.py: shared helpers (channel hint and bot recognition, F1 data and game, community helpers and
#   archive, ingress support for the Home Assistant sidebar, Bots and Games pages, ...);
# - local_shared/local_data: word lists, quotes and facts for the games;
# - local_commands: the extra commands (NL/BE data, games, F1, rptr, ...);
# - local_service_plugins: the extra services (notifications, room server login, contact cleanup, HA bridge and
#   repeater, heartbeat, F1, reminders, community archive, ...);
# - local_shared/local_translations: our translation catalogue (nl/en/de/fr), merged over upstream's own;
# - local_web: the Bots and Games pages of the dashboard.
# None of these files is also changed by a patch, so the order of the patch step and these copies does not matter.
COPY local_shared/*.py ./modules/
COPY local_shared/local_data/ ./modules/local_data/
COPY local_commands/*.py ./modules/commands/
COPY local_service_plugins/*.py ./modules/service_plugins/
COPY local_shared/local_translations/ ./local/translations/
COPY local_web/*.html ./modules/web_viewer/templates/

COPY generate_config.py /opt/generate_config.py
COPY data_transfer.py /opt/data_transfer.py
COPY run.sh /
RUN chmod a+x /run.sh

CMD [ "/run.sh" ]
