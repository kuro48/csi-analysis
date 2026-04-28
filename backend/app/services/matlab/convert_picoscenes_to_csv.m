function convert_picoscenes_to_csv(inputPath, outputCsv, maxSubcarriers)
% Read a .csv file and write selected subcarriers to an output CSV consumed
% by the Python pipeline.
%
% Arguments:
%   inputPath      - path to an input .csv file with a 'timestamp' column
%                    (nanoseconds) and numeric subcarrier amplitude columns
%                    named by their subcarrier index.
%   outputCsv      - path for the output CSV file.
%   maxSubcarriers - maximum number of subcarriers to retain (default: 245).
%
% The function applies subcarrier selection identical to the old PicoScenes
% path so the downstream Python pipeline receives the same data shape.
%
% --- OLD IMPLEMENTATION (.csi / PicoScenes MATLAB Toolbox) ---------------
% % Convert a PicoScenes .csi file to a CSV consumed by the Python pipeline.
% %
% % The PicoScenes MATLAB toolbox exposes opencsi(FILE_PATH). Depending on the
% % toolbox version and frame contents, the parsed bundle may be a cell array or
% % a struct array, and CSI values may be exposed as Mag or complex CSI. This
% % helper keeps the extraction defensive and writes timestamp plus amplitude
% % columns named by subcarrier index.
% %
% % if nargin < 3 || isempty(maxSubcarriers)
% %     maxSubcarriers = 245;
% % end
% %
% % beforeVars = evalin('base', 'who');
% % opencsi(inputPath);
% % afterVars = evalin('base', 'who');
% % newVars = setdiff(afterVars, beforeVars);
% %
% % if isempty(newVars)
% %     [~, baseName, ~] = fileparts(inputPath);
% %     candidate = matlab.lang.makeValidName(baseName);
% %     if evalin('base', sprintf('exist(''%s'', ''var'')', candidate)) == 1
% %         parsed = evalin('base', candidate);
% %     else
% %         error('convert_picoscenes_to_csv:NoParsedVariable', ...
% %             'opencsi did not create a parse result variable.');
% %     end
% % else
% %     parsed = evalin('base', newVars{end});
% % end
% %
% % nFrames = frame_count(parsed);
% % if nFrames == 0
% %     error('convert_picoscenes_to_csv:NoFrames', 'PicoScenes file contains no frames.');
% % end
% %
% % firstFrame = get_frame(parsed, 1);
% % [firstTone, subcarrierIndices] = extract_tone_vector(firstFrame);
% % numTones = numel(firstTone);
% % if numTones == 0 || numel(subcarrierIndices) ~= numTones
% %     error('convert_picoscenes_to_csv:InvalidMetadata', ...
% %         'Invalid CSI metadata: numTones/SubcarrierIndex mismatch.');
% % end
% %
% % selected = select_subcarriers(subcarrierIndices, maxSubcarriers);
% % selectedIndices = subcarrierIndices(selected);
% %
% % values = nan(nFrames, numel(selected));
% % timestamps = nan(nFrames, 1);
% % valid = false(nFrames, 1);
% % fallbackNs = 0;
% %
% % for i = 1:nFrames
% %     frame = get_frame(parsed, i);
% %     try
% %         [toneVector, frameSubcarrierIndices] = extract_tone_vector(frame);
% %         if numel(toneVector) ~= numTones || any(frameSubcarrierIndices(:) ~= subcarrierIndices(:))
% %             continue;
% %         end
% %         values(i, :) = double(toneVector(selected));
% %         timestamps(i) = extract_timestamp_ns(frame, fallbackNs);
% %         fallbackNs = timestamps(i) + 10000000;
% %         valid(i) = true;
% %     catch
% %         % Skip malformed frames; Python will fail if nothing valid remains.
% %     end
% % end
% %
% % values = values(valid, :);
% % timestamps = timestamps(valid);
% % if isempty(timestamps)
% %     error('convert_picoscenes_to_csv:NoValidFrames', ...
% %         'No valid PicoScenes frames could be converted.');
% % end
% %
% % write_csv(outputCsv, timestamps, selectedIndices, values);
% -------------------------------------------------------------------------

if nargin < 3 || isempty(maxSubcarriers)
    maxSubcarriers = 245;
end

% --- Read input CSV -------------------------------------------------------
opts = detectImportOptions(inputPath, 'VariableNamingRule', 'preserve');
T = readtable(inputPath, opts);

varNames = T.Properties.VariableNames;

% Locate the timestamp column (case-insensitive)
tsIdx = find(strcmpi(varNames, 'timestamp'), 1);
if isempty(tsIdx)
    error('convert_picoscenes_to_csv:NoTimestamp', ...
        'Input CSV must have a "timestamp" column.');
end
timestamps = double(T{:, tsIdx});

% Collect numeric subcarrier columns (column name is a valid integer)
subcarrierIndices = [];
subcarrierCols    = [];
for k = 1:numel(varNames)
    if k == tsIdx
        continue;
    end
    val = str2double(varNames{k});
    if ~isnan(val) && isfinite(val)
        subcarrierIndices(end+1) = val; %#ok<AGROW>
        subcarrierCols(end+1)    = k;   %#ok<AGROW>
    end
end

if isempty(subcarrierIndices)
    error('convert_picoscenes_to_csv:NoSubcarriers', ...
        'No numeric subcarrier columns found in input CSV.');
end

subcarrierIndices = subcarrierIndices(:);

% --- Subcarrier selection (same logic as the old PicoScenes path) ---------
selected = select_subcarriers(subcarrierIndices, maxSubcarriers);
selectedIndices = subcarrierIndices(selected);

values = zeros(height(T), numel(selected));
for k = 1:numel(selected)
    values(:, k) = double(T{:, subcarrierCols(selected(k))});
end

% Remove rows where the timestamp is NaN
validRows = ~isnan(timestamps);
timestamps = timestamps(validRows);
values     = values(validRows, :);

if isempty(timestamps)
    error('convert_picoscenes_to_csv:NoValidRows', ...
        'No valid rows remain after filtering NaN timestamps.');
end

% --- Write output CSV -----------------------------------------------------
write_csv(outputCsv, timestamps, selectedIndices, values);
end

% =========================================================================
% Helper functions (shared between old and new paths)
% =========================================================================

% --- OLD PicoScenes helpers (kept for reference) -------------------------
% function n = frame_count(parsed)
% if iscell(parsed)
%     n = numel(parsed);
% elseif isstruct(parsed)
%     n = numel(parsed);
% else
%     n = 0;
% end
% end
%
% function frame = get_frame(parsed, idx)
% if iscell(parsed)
%     frame = parsed{idx};
% else
%     frame = parsed(idx);
% end
% end
%
% function [toneVector, subcarrierIndices] = extract_tone_vector(frame)
% csi = get_field_ci(frame, 'CSI');
% rx = get_field_ci(frame, 'RxSBasic');
%
% subcarrierIndices = get_field_ci(csi, 'SubcarrierIndex');
% subcarrierIndices = double(subcarrierIndices(:));
% numTones = numel(subcarrierIndices);
%
% numSTS = get_numeric_field(rx, 'numSTS', 1);
% numRx = get_numeric_field(rx, 'numRx', get_numeric_field(csi, 'numRx', 1));
%
% if has_field_ci(csi, 'Mag')
%     raw = double(get_field_ci(csi, 'Mag'));
% else
%     raw = abs(double(get_field_ci(csi, 'CSI')));
% end
%
% if isvector(raw)
%     if numel(raw) ~= numTones * numSTS * numRx
%         error('convert_picoscenes_to_csv:UnexpectedCsiSize', 'Unexpected CSI vector size.');
%     end
%     csiMatrix = reshape(raw, [numTones, numSTS, numRx]);
%     toneVector = csiMatrix(:, 1, 1);
% else
%     dims = size(raw);
%     if dims(1) ~= numTones
%         raw = reshape(raw, [numTones, numel(raw) / numTones]);
%     end
%     toneVector = raw(:, 1);
% end
%
% toneVector = double(toneVector(:));
% end
%
% function timestampNs = extract_timestamp_ns(frame, fallbackNs)
% rx = get_field_ci(frame, 'RxSBasic');
% if ~isempty(rx) && has_field_ci(rx, 'systemns')
%     timestampNs = double(get_field_ci(rx, 'systemns'));
% else
%     timestampNs = double(fallbackNs);
% end
% end
%
% function value = get_numeric_field(s, name, defaultValue)
% if isempty(s) || ~has_field_ci(s, name)
%     value = defaultValue;
% else
%     value = double(get_field_ci(s, name));
%     if isempty(value)
%         value = defaultValue;
%     else
%         value = value(1);
%     end
% end
% end
%
% function tf = has_field_ci(s, name)
% if isempty(s) || ~isstruct(s)
%     tf = false;
%     return;
% end
% names = fieldnames(s);
% tf = any(strcmpi(names, name));
% end
%
% function value = get_field_ci(s, name)
% if isempty(s) || ~isstruct(s)
%     value = [];
%     return;
% end
% names = fieldnames(s);
% idx = find(strcmpi(names, name), 1);
% if isempty(idx)
%     value = [];
% else
%     value = s.(names{idx});
% end
% end
% -------------------------------------------------------------------------

function selected = select_subcarriers(subcarrierIndices, maxSubcarriers)
if numel(subcarrierIndices) <= maxSubcarriers
    selected = (1:numel(subcarrierIndices)).';
    return;
end

nonZero = find(subcarrierIndices ~= 0);
if numel(nonZero) >= maxSubcarriers
    [~, order] = sort(abs(subcarrierIndices(nonZero)));
    ranked = nonZero(order(1:maxSubcarriers));
else
    [~, order] = sort(abs(subcarrierIndices));
    ranked = order(1:maxSubcarriers);
end
selected = sort(ranked(:));
end

function write_csv(outputCsv, timestamps, subcarrierIndices, values)
fid = fopen(outputCsv, 'w');
if fid < 0
    error('convert_picoscenes_to_csv:OpenOutputFailed', 'Could not open output CSV.');
end
cleanup = onCleanup(@() fclose(fid));

fprintf(fid, 'timestamp');
for j = 1:numel(subcarrierIndices)
    fprintf(fid, ',%d', round(subcarrierIndices(j)));
end
fprintf(fid, '\n');

for i = 1:numel(timestamps)
    fprintf(fid, '%.0f', timestamps(i));
    for j = 1:size(values, 2)
        fprintf(fid, ',%.17g', values(i, j));
    end
    fprintf(fid, '\n');
end
end
